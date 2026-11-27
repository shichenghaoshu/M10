from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .doctor import report
from .media import download_mediamtx, executable
from .settings import ROOT, get_token, load_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description="M10 + Dreamupers one-command runtime")
    parser.add_argument("command", choices=["demo", "esp32", "radxa", "doctor"], nargs="?", default="demo")
    parser.add_argument("--profile", choices=["demo", "esp32", "radxa"], default="demo", help="Profile for doctor")
    parser.add_argument("--config", help="Local YAML overrides")
    parser.add_argument("--serial", help="ESP32 serial device")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--arm", action="store_true", help="Enable the selected physical motor backend")
    parser.add_argument("--stream", action="store_true", help="Enable V4L2/FFmpeg/MediaMTX, downloading MediaMTX if missing")
    parser.add_argument("--fetch-media", action="store_true", help="Install the pinned, verified Linux MediaMTX binary")
    args = parser.parse_args(argv)
    profile = args.profile if args.command == "doctor" else args.command
    settings = load_settings(profile, args.config)
    settings["arm"] = args.arm
    for name, value in [("serial_port", args.serial), ("host", args.host), ("port", args.port)]:
        if value is not None:
            settings[name] = value
    if args.stream:
        settings["media"]["enabled"] = True
    if ((args.stream and args.command != "doctor") or args.fetch_media) and not executable(settings["media"]["mediamtx"]):
        destination = Path(settings["media"]["mediamtx"])
        if not destination.is_absolute():
            destination = ROOT / destination
        print("Installing pinned MediaMTX archive (SHA-256 verified)...", flush=True)
        download_mediamtx(destination)
    if args.command == "doctor":
        result = report(settings)
        print(json.dumps(result, indent=2))
        return 0 if result["ready"] else 1
    from .app import create_app
    import uvicorn
    data = ROOT / ".m10"
    token = get_token(data)
    app = create_app(settings, token, data)
    host = "127.0.0.1" if settings["host"] in {"0.0.0.0", "::"} else settings["host"]
    print("M10 profile: " + profile + (" (simulated motors)" if profile == "demo" else " (hardware)"), flush=True)
    print("Open http://" + host + ":" + str(settings["port"]) + "/#token=" + token, flush=True)
    print("Ctrl+C stops owned services and requests motor STOP.", flush=True)
    uvicorn.run(app, host=settings["host"], port=settings["port"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print("M10: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
