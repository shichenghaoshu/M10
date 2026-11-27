from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import platform

from .media import Media
from .settings import ROOT, UPSTREAM


def check_upstream() -> dict:
    manifest = json.loads((UPSTREAM.parent / "UPSTREAM.json").read_text())
    bad = []
    for entry in manifest["files"]:
        path = UPSTREAM / entry["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            bad.append(entry["path"])
    return {"ready": not bad, "commit": manifest["commit"], "mismatches": bad}


def report(settings: dict) -> dict:
    upstream = check_upstream()
    checks = {"upstream": upstream,
              "face_videos": {"ready": all((ROOT / "video" / (str(i) + ".mp4")).is_file() for i in range(1, 11))}}
    if settings["profile"] == "esp32":
        checks["serial"] = {"ready": Path(settings["serial_port"]).exists(), "device": settings["serial_port"]}
    if settings["profile"] == "radxa":
        checks["linux"] = {"ready": platform.system() == "Linux"}
        checks["gpio"] = {"ready": Path("/dev/gpiochip3").exists(), "api": "gpiod 1.x"}
        checks["pwm"] = {"ready": all(Path("/sys/class/pwm/pwmchip" + str(settings["gpio"][name])).exists() for name in ["pwm_a_channel", "pwm_b_channel"])}
        checks["gpio_dependencies"] = {"ready": all(importlib.util.find_spec(name) is not None for name in ["gpiod", "periphery"])}
    if settings["media"]["enabled"]:
        checks["media"] = Media(settings["media"], ROOT / ".m10").preflight()
    return {"profile": settings["profile"], "ready": all(c["ready"] for c in checks.values()),
            "armed": settings["arm"], "checks": checks}
