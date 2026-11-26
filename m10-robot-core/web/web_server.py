from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


def create_app(robot_core) -> FastAPI:
    base_path = Path(__file__).resolve().parent
    app = FastAPI(title="M10 Robot Core", version="0.1.0")
    templates = Jinja2Templates(directory=str(base_path / "templates"))
    app.mount("/static", StaticFiles(directory=str(base_path / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "device": robot_core.config["device"],
            },
        )

    @app.get("/api/status")
    async def get_status():
        return JSONResponse(robot_core.build_status())

    @app.get("/api/hardware")
    async def get_hardware():
        return JSONResponse(robot_core.build_status()["hardware"])

    @app.get("/api/esp32/status")
    async def get_esp32_status():
        return JSONResponse(robot_core.esp32_bridge.get_status())

    @app.post("/api/control/forward")
    async def control_forward():
        return JSONResponse(robot_core.command_dispatcher.forward())

    @app.post("/api/control/backward")
    async def control_backward():
        return JSONResponse(robot_core.command_dispatcher.backward())

    @app.post("/api/control/left")
    async def control_left():
        return JSONResponse(robot_core.command_dispatcher.left())

    @app.post("/api/control/right")
    async def control_right():
        return JSONResponse(robot_core.command_dispatcher.right())

    @app.post("/api/control/stop")
    async def control_stop():
        return JSONResponse(robot_core.command_dispatcher.stop())

    @app.post("/api/control/status")
    async def control_status():
        return JSONResponse(robot_core.command_dispatcher.status())

    @app.post("/api/video/snapshot")
    async def video_snapshot():
        return JSONResponse(robot_core.command_dispatcher.snapshot())

    @app.post("/api/display/face/{face_name}")
    async def display_face(face_name: str):
        return JSONResponse(robot_core.command_dispatcher.display_face(face_name))

    @app.post("/api/audio/test")
    async def audio_test():
        return JSONResponse(robot_core.command_dispatcher.audio_test())

    @app.post("/api/server/heartbeat")
    async def server_heartbeat():
        return JSONResponse(robot_core.command_dispatcher.heartbeat())

    return app
