from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = Path(os.getenv("M10_FACE_VIDEO_DIR", str(BASE_DIR.parent / "video"))).resolve()
DEFAULT_STATE_ID = int(os.getenv("M10_FACE_DEFAULT_STATE", "1"))
API_TOKEN = os.getenv("M10_FACE_API_TOKEN", "").strip()
SERVER_URL = os.getenv("M10_FACE_SERVER_URL", "").strip()
SERVER_TOKEN = os.getenv("M10_FACE_SERVER_TOKEN", "").strip()
POLL_INTERVAL_SECONDS = max(0.2, float(os.getenv("M10_FACE_POLL_INTERVAL", "1.0")))
SERVER_TIMEOUT_SECONDS = max(1.0, float(os.getenv("M10_FACE_SERVER_TIMEOUT", "15.0")))


@dataclass(frozen=True)
class FaceState:
    id: int
    key: str
    name: str
    video: str

    def public(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["video_url"] = "/media/{}".format(self.video)
        return payload


STATES: List[FaceState] = [
    FaceState(1, "idle_blink", "默认待机·灵动眨眼", "1.mp4"),
    FaceState(2, "idle_breathe", "极简待机·呼吸灯效果", "2.mp4"),
    FaceState(3, "happy", "猫咪开心·撒娇表情", "3.mp4"),
    FaceState(4, "excited", "超级兴奋·星星眼", "4.mp4"),
    FaceState(5, "playful", "调皮眨眼·互动回应", "5.mp4"),
    FaceState(6, "sleep", "睡眠模式·安静打呼", "6.mp4"),
    FaceState(7, "curious", "好奇疑惑·探索状态", "7.mp4"),
    FaceState(8, "listening", "聆听模式·声波响应", "8.mp4"),
    FaceState(9, "thinking", "思考模式·三点循环", "9.mp4"),
    FaceState(10, "low_battery", "低电量·委屈求充电", "10.mp4"),
]

STATE_BY_ID = {state.id: state for state in STATES}
STATE_BY_KEY = {state.key: state for state in STATES}
ALIASES = {
    "idle": 1,
    "standby": 1,
    "blink": 1,
    "breathe": 2,
    "breathing": 2,
    "joy": 3,
    "cat_happy": 3,
    "super_excited": 4,
    "wink": 5,
    "naughty": 5,
    "sleeping": 6,
    "question": 7,
    "explore": 7,
    "listen": 8,
    "voice": 8,
    "think": 9,
    "loading": 9,
    "battery_low": 10,
    "charging_needed": 10,
    "默认待机": 1,
    "极简待机": 2,
    "开心": 3,
    "兴奋": 4,
    "调皮": 5,
    "睡眠": 6,
    "好奇": 7,
    "聆听": 8,
    "思考": 9,
    "低电量": 10,
}


def normalize_state(value: Union[int, str]) -> FaceState:
    if isinstance(value, bool):
        raise ValueError("state must be an id from 1 to 10 or a state key")

    if isinstance(value, int):
        state_id = value
    else:
        text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        if text.endswith(".mp4") and text[:-4].isdigit():
            text = text[:-4]
        if text.isdigit():
            state_id = int(text)
        elif text in STATE_BY_KEY:
            return STATE_BY_KEY[text]
        elif text in ALIASES:
            state_id = ALIASES[text]
        else:
            raise ValueError("unknown state: {}".format(value))

    if state_id not in STATE_BY_ID:
        raise ValueError("state id must be between 1 and 10")
    return STATE_BY_ID[state_id]


def extract_server_command(payload: Any) -> Optional[Dict[str, Any]]:
    """Accept common server response shapes without coupling to one backend."""
    if not isinstance(payload, dict):
        return None
    for container_key in ("data", "command", "params", "payload"):
        nested = payload.get(container_key)
        if isinstance(nested, dict):
            candidate = extract_server_command(nested)
            if candidate:
                return candidate

    state_value = None
    for key in ("state", "state_id", "face", "expression", "mode", "video"):
        if key in payload:
            state_value = payload[key]
            break
    if state_value is None:
        return None

    duration_ms = int(payload.get("duration_ms", payload.get("duration", 0)) or 0)
    transition_ms = int(payload.get("transition_ms", 140) or 0)
    return {
        "state": state_value,
        "duration_ms": min(max(duration_ms, 0), 3_600_000),
        "transition_ms": min(max(transition_ms, 0), 2_000),
    }


class StateCommand(BaseModel):
    state: Union[int, str]
    duration_ms: int = Field(default=0, ge=0, le=3_600_000)
    transition_ms: int = Field(default=140, ge=0, le=2_000)


class FaceController:
    def __init__(self, default_state_id: int) -> None:
        self.default_state = normalize_state(default_state_id)
        self.current_state = self.default_state
        self.revision = 0
        self.source = "startup"
        self.transition_ms = 0
        self.changed_at = time.time()
        self.expires_at: Optional[float] = None
        self.clients: Set[WebSocket] = set()
        self._reset_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "type": "state",
            "state": self.current_state.public(),
            "revision": self.revision,
            "source": self.source,
            "transition_ms": self.transition_ms,
            "changed_at": self.changed_at,
            "expires_at": self.expires_at,
        }

    async def set_state(
        self,
        value: Union[int, str],
        duration_ms: int = 0,
        transition_ms: int = 140,
        source: str = "api",
    ) -> Dict[str, Any]:
        state = normalize_state(value)
        async with self._lock:
            if self._reset_task and self._reset_task is not asyncio.current_task():
                self._reset_task.cancel()
            self._reset_task = None

            self.current_state = state
            self.revision += 1
            self.source = source
            self.transition_ms = transition_ms
            self.changed_at = time.time()
            self.expires_at = self.changed_at + duration_ms / 1000.0 if duration_ms else None
            snapshot = self.snapshot()

            if duration_ms:
                revision = self.revision
                self._reset_task = asyncio.create_task(self._reset_after(duration_ms, revision))

        await self.broadcast(snapshot)
        return snapshot

    async def _reset_after(self, duration_ms: int, revision: int) -> None:
        try:
            await asyncio.sleep(duration_ms / 1000.0)
            if revision == self.revision:
                await self.set_state(self.default_state.id, source="duration_expired")
        except asyncio.CancelledError:
            return

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        stale: List[WebSocket] = []
        for client in list(self.clients):
            try:
                await client.send_json(payload)
            except Exception:
                stale.append(client)
        for client in stale:
            self.clients.discard(client)


controller = FaceController(DEFAULT_STATE_ID)
logger = logging.getLogger("m10-face-ui")


def fetch_server_payload() -> Any:
    headers = {"Accept": "application/json", "User-Agent": "m10-face-ui/1.0"}
    if SERVER_TOKEN:
        headers["Authorization"] = "Bearer {}".format(SERVER_TOKEN)
    request = urllib.request.Request(SERVER_URL, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


async def poll_server() -> None:
    last_signature = ""
    last_success = time.monotonic()
    fallback_applied = False
    while True:
        try:
            loop = asyncio.get_running_loop()
            payload = await loop.run_in_executor(None, fetch_server_payload)
            last_success = time.monotonic()
            fallback_applied = False
            command = extract_server_command(payload)
            if command:
                signature = json.dumps(command, sort_keys=True, ensure_ascii=False)
                if signature != last_signature:
                    await controller.set_state(source="server_poll", **command)
                    last_signature = signature
        except asyncio.CancelledError:
            return
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
            logger.warning("server poll failed: %s", exc)
            if time.monotonic() - last_success >= SERVER_TIMEOUT_SECONDS and not fallback_applied:
                await controller.set_state(controller.default_state.id, source="server_timeout")
                fallback_applied = True
                last_signature = ""
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    missing = [state.video for state in STATES if not (VIDEO_DIR / state.video).is_file()]
    if missing:
        raise RuntimeError("missing video files in {}: {}".format(VIDEO_DIR, ", ".join(missing)))
    poll_task = asyncio.create_task(poll_server()) if SERVER_URL else None
    try:
        yield
    finally:
        if poll_task:
            poll_task.cancel()
            await asyncio.gather(poll_task, return_exceptions=True)


app = FastAPI(title="M10 Face UI", version="1.0.0", lifespan=lifespan)
app.mount("/media", StaticFiles(directory=str(VIDEO_DIR)), name="media")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def require_token(authorization: Optional[str]) -> None:
    if not API_TOKEN:
        return
    if authorization != "Bearer {}".format(API_TOKEN):
        raise HTTPException(status_code=401, detail="invalid API token")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "m10-face-ui",
        "video_dir": str(VIDEO_DIR),
        "server_polling": bool(SERVER_URL),
        "connected_displays": len(controller.clients),
    }


@app.get("/api/v1/states")
async def list_states() -> Dict[str, Any]:
    return {"states": [state.public() for state in STATES]}


@app.get("/api/v1/state")
async def get_state() -> Dict[str, Any]:
    return controller.snapshot()


@app.post("/api/v1/state")
@app.put("/api/v1/state")
@app.post("/api/state")
async def set_state(command: StateCommand, authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_token(authorization)
    try:
        return await controller.set_state(
            command.state,
            duration_ms=command.duration_ms,
            transition_ms=command.transition_ms,
            source="api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    controller.clients.add(websocket)
    await websocket.send_json(controller.snapshot())
    try:
        while True:
            payload = await websocket.receive_json()
            if API_TOKEN and websocket.query_params.get("token") != API_TOKEN:
                await websocket.send_json({"type": "error", "detail": "read-only connection"})
                continue
            command = extract_server_command(payload)
            if not command:
                await websocket.send_json({"type": "error", "detail": "state parameter is required"})
                continue
            try:
                await controller.set_state(source="websocket", **command)
            except ValueError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
    except WebSocketDisconnect:
        pass
    finally:
        controller.clients.discard(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("M10_FACE_HOST", "0.0.0.0"),
        port=int(os.getenv("M10_FACE_PORT", "8765")),
        reload=False,
    )
