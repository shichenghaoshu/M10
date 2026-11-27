from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import importlib.util
import json
import logging
from pathlib import Path
import re
import secrets
import sys
import threading
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
import httpx

from .control import Control
from .doctor import check_upstream
from .media import Media
from .motors import Motor, load_upstream
from .settings import ROOT, UPSTREAM

LOG = logging.getLogger("m10.runtime")
WEB = ROOT / "m10_runtime/web"


class MotionRequest(BaseModel):
    action: str
    client_id: str = Field(default="", max_length=128)


class SpeedRequest(BaseModel):
    speed: int = Field(ge=1, le=60, strict=True)


class BitrateRequest(BaseModel):
    mbps: int = Field(ge=1, le=20, strict=True)


def face_module(token: str):
    name = "m10_runtime_face_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "m10-face-ui/app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolves module annotations here.
    spec.loader.exec_module(module)
    module.API_TOKEN = token
    # Unified runtime owns its lifecycle; do not start a second remote poller.
    module.SERVER_URL = ""
    return module


def legacy_page() -> str:
    page = (UPSTREAM / "templates/ws_index.html").read_text()
    page = page.replace("new WebSocket('ws://10.0.0.229:8080/control')",
                        "new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/control/ws', ['m10', 'm10.token.' + sessionStorage.getItem('m10-control-token')])")
    page = page.replace("'http://10.0.0.229:8888/stream/index.m3u8'", "location.origin + '/stream/index.m3u8'")
    page = page.replace("hls.js@latest", "hls.js@1.6.13")
    page = page.replace("function startControl(action) {\n            sendControl(action);",
                        "function startControl(action) {\n            m10Hold(action);")
    page = page.replace("function stopControl() {\n            sendControl('stop');",
                        "function stopControl() {\n            m10Release(true);")
    page = page.replace("async function MuststopControl() {", "async function MuststopControl() { m10Release(false);")
    page = page.replace(" : '0.00';", " : '\u2014';")
    page = page.replace("const power = (isFinite(voltage) && isFinite(current)) ? (voltage * current) : 0;",
                        "const power = (isFinite(voltage) && isFinite(current)) ? (voltage * current) : NaN;")
    page = page.replace("powerElem.innerText = power.toFixed(2);", "powerElem.innerText = isFinite(power) ? power.toFixed(2) : '\u2014';")
    adapter = "<script>" + (WEB / "legacy-adapter.js").read_text() + "</script>"
    return page.replace("<head>", "<head>" + adapter, 1)


def create_app(settings: dict, token: str, data: Path | None = None, motor=None) -> FastAPI:
    data = data or ROOT / ".m10"
    motor = motor or Motor(settings)
    control = Control(motor, settings["lease_ms"], settings["speed_percent"])
    media = Media(settings["media"], data)
    face = face_module(token)
    upstream = check_upstream()
    if not upstream["ready"]:
        raise RuntimeError("Vendored upstream hash check failed")
    sensor = {"device": None, "error": None}
    stop_event = threading.Event()

    def watchdog():
        while not stop_event.wait(0.025):
            try:
                control.tick()
            except Exception:
                LOG.exception("Motion deadline expired; stop failed")

    @asynccontextmanager
    async def lifespan(app):
        stop_event.clear()
        try:
            motor.connect()
        except Exception as exc:
            motor.last_error = str(exc)
            LOG.warning("Motor unavailable: %s", exc)
        if settings["sensor"]["enabled"]:
            try:
                cfg = settings["sensor"]
                sensor["device"] = load_upstream("vc").INA226(dev=cfg["device"], address=cfg["address"])
                sensor["device"].configure()
            except Exception as exc:
                sensor["error"] = str(exc)
        thread = threading.Thread(target=watchdog, name="m10-motion-deadline", daemon=True)
        thread.start()
        try:
            async with face.app.router.lifespan_context(face.app):
                yield
        finally:
            stop_event.set()
            thread.join(timeout=1)
            media.stop()
            try:
                motor.close()
            except Exception:
                LOG.exception("Motor close failed")
            if sensor["device"]:
                sensor["device"].i2c.close()

    app = FastAPI(title="M10 Replica", lifespan=lifespan)
    app.state.control, app.state.media, app.state.motor = control, media, motor

    def valid(candidate: str | None) -> bool:
        return bool(candidate) and secrets.compare_digest(candidate, token)

    def authorized(request: Request):
        value = request.headers.get("Authorization", "")
        if not value.startswith("Bearer ") or not valid(value[7:]):
            raise HTTPException(401, "Pairing token required")

    def run(call, *args):
        try:
            return call(*args)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (RuntimeError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc

    def telemetry():
        voltage = current = None
        if sensor["device"]:
            try:
                voltage = sensor["device"].bus_voltage
                current = sensor["device"].current
            except Exception as exc:
                sensor["error"] = str(exc)
        return {"bus_voltage": voltage, "current": current, "cpu_percent": None,
                "mem_percent": None, "cpu_temp": None, "sensor_error": sensor["error"]}

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (WEB / "index.html").read_text()

    @app.get("/console.js")
    def console_js():
        return FileResponse(WEB / "console.js", media_type="application/javascript")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "m10-replica", "profile": settings["profile"],
                "motor_ready": motor.healthy, "simulated": settings["profile"] == "demo"}

    @app.post("/api/runtime/pair", dependencies=[Depends(authorized)])
    def pair(request: Request):
        response = Response(content='{"ok":true}', media_type="application/json")
        response.set_cookie("m10_media", token, httponly=True, samesite="strict", secure=request.url.scheme == "https")
        return response

    @app.get("/api/runtime/status", dependencies=[Depends(authorized)])
    def status():
        return {"profile": settings["profile"], "control": control.status(), "media": media.status(),
                "upstream": upstream, "sensors": telemetry(), "tracking": "not_integrated"}

    @app.post("/api/runtime/control", dependencies=[Depends(authorized)])
    @app.post("/control", dependencies=[Depends(authorized)])
    def command(body: MotionRequest):
        if body.action != "stop" and not body.client_id:
            raise HTTPException(422, "client_id required for HTTP motion")
        return {"status": "ok", "control": run(control.command, body.action, "http:" + body.client_id)}

    @app.post("/set_speed", dependencies=[Depends(authorized)])
    def speed(body: SpeedRequest):
        run(control.set_speed, body.speed)
        return {"status": "ok", "speed": body.speed}

    @app.post("/api/runtime/emergency_stop", dependencies=[Depends(authorized)])
    def emergency():
        return run(control.emergency)

    @app.post("/api/runtime/clear_emergency_stop", dependencies=[Depends(authorized)])
    def clear_emergency():
        return run(control.clear_emergency)

    @app.post("/api/runtime/reconnect", dependencies=[Depends(authorized)])
    def reconnect():
        with control.lock:
            control.owner, control.expires, control.action = None, 0, "stop"
            run(motor.connect)
        return control.status()

    @app.websocket("/control/ws")
    async def control_ws(socket: WebSocket):
        protocols = socket.headers.get("sec-websocket-protocol", "").split(",")
        credentials = next((p.strip()[10:] for p in protocols if p.strip().startswith("m10.token.")), "")
        if not valid(credentials):
            await socket.close(code=4401)
            return
        await socket.accept(subprotocol="m10")
        owner = "ws:" + uuid.uuid4().hex
        try:
            while True:
                try:
                    payload = await socket.receive_json()
                    if not isinstance(payload, dict):
                        raise ValueError("Expected a control object")
                    result = await asyncio.to_thread(control.command, payload.get("action"), owner)
                    await socket.send_json({"status": "ok", "control": result})
                except (ValueError, RuntimeError, OSError) as exc:
                    await socket.send_json({"status": "error", "message": str(exc)})
        except WebSocketDisconnect:
            pass
        finally:
            try:
                # Complete the bounded STOP before cancellation can end this handler.
                # MCU action deadlines remain independent of this host cleanup.
                control.disconnected(owner)
            except Exception:
                LOG.exception("Controller disconnect stop failed")

    @app.post("/status_and_heartbeat", dependencies=[Depends(authorized)])
    def legacy_status():
        # Observing status never renews or creates a motion lease.
        now = int(time.time() * 1000)
        values = telemetry()
        for key in ["cpu_percent", "mem_percent", "cpu_temp"]:
            if values[key] is None:
                values[key] = "\u2014"
        return {"status": "ok", **values, "t2": now, "t3": int(time.time() * 1000)}

    @app.get("/dreamupers", response_class=HTMLResponse)
    def dreamupers():
        return legacy_page()

    @app.get("/favicon.ico")
    @app.get("/static/icon_128.png")
    @app.get("/static/icon_256.png")
    def icon():
        return Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect width="128" height="128" rx="26" fill="#183c31"/><text x="64" y="78" fill="#f6f5eb" font-size="42" text-anchor="middle">M10</text></svg>', media_type="image/svg+xml")

    @app.post("/start_stream", dependencies=[Depends(authorized)])
    def start_stream():
        return {"status": "ok", "media": run(media.start)}

    @app.post("/stop_stream", dependencies=[Depends(authorized)])
    def stop_stream():
        return {"status": "ok", "media": media.stop()}

    @app.post("/set_bitrate", dependencies=[Depends(authorized)])
    def bitrate(body: BitrateRequest):
        media.config["bitrate_mbps"] = body.mbps
        return {"status": "ok", "applies_on_next_stream_start": True}

    @app.post("/set_laser", dependencies=[Depends(authorized)])
    def laser():
        raise HTTPException(501, "Laser control is not exposed by the integrated runtime")

    @app.post("/sleep", dependencies=[Depends(authorized)])
    def sleep():
        raise HTTPException(501, "Host suspend is not exposed by the integrated runtime")

    @app.get("/stream/{path:path}")
    async def stream(path: str, request: Request):
        header = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not valid(header) and not valid(request.cookies.get("m10_media")):
            raise HTTPException(401, "Pair before opening preview")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path) or ".." in path.split("/") or path.startswith("/"):
            raise HTTPException(400, "Invalid stream path")
        if not media.status()["running"]:
            raise HTTPException(503, "Stream not running")
        url = "http://127.0.0.1:" + str(media.config["hls_port"]) + "/stream/" + path
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                async with client.stream("GET", url, params=request.query_params) as reply:
                    chunks = []
                    total = 0
                    async for chunk in reply.aiter_bytes():
                        total += len(chunk)
                        if total > 32 * 1024 * 1024:
                            raise HTTPException(502, "Media segment too large")
                        chunks.append(chunk)
                    if reply.status_code == 200:
                        media.last_hls_at = time.monotonic()
                    return Response(b"".join(chunks), status_code=reply.status_code,
                                    media_type=reply.headers.get("content-type", "application/octet-stream"),
                                    headers={"Cache-Control": "no-store"})
        except httpx.HTTPError as exc:
            raise HTTPException(503, "HLS output not ready") from exc

    @app.get("/face")
    def face_page():
        return FileResponse(ROOT / "m10-face-ui/static/index.html")

    app.mount("/", face.app)
    return app
