#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn
import yaml

from services.robot_core import RobotCore
from web.web_server import create_app


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def print_startup_summary(robot_core: RobotCore, host: str | None = None, port: int | None = None) -> None:
    status = robot_core.build_status()
    hardware = status["hardware"]
    server = status["server"]
    web_host = host or status["web"]["host"]
    web_port = port or status["web"]["port"]

    print("M10 Robot Core starting...")
    print("Config loaded.")
    print("Hardware discovery complete.")
    print(f"ESP32: {hardware['esp32']['status']}")
    print(f"Camera: {hardware['camera']['status']}")
    print(f"Display: {hardware['display']['status']}")
    print(f"Audio input: {hardware['audio_input']['status']}")
    print(f"Audio output: {hardware['audio_output']['status']}")
    print(f"Server: {server['status']}")
    print(f"Web console: http://{web_host}:{web_port}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run M10 Robot Core.")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--check", action="store_true", help="Run startup checks only and exit")
    parser.add_argument("--host", help="Override web host")
    parser.add_argument("--port", type=int, help="Override web port")
    args = parser.parse_args()

    base_path = Path(__file__).resolve().parent
    config_path = (base_path / args.config).resolve()
    config = load_config(config_path)

    robot_core = RobotCore(config=config, base_path=base_path)
    robot_core.initialize()
    print_startup_summary(robot_core, host=args.host, port=args.port)

    if args.check:
        robot_core.logger.info("Startup check completed successfully.")
        return 0

    app = create_app(robot_core)
    host = args.host or config["web"]["host"]
    port = args.port or int(config["web"]["port"])
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
