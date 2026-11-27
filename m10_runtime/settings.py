from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import secrets
import os

import yaml

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "third_party/dreamupers/rk3566-ipc-car-public"


def merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if key not in result:
            raise ValueError("Unknown setting: " + key)
        if isinstance(result[key], dict):
            if not isinstance(value, dict):
                raise ValueError("Expected settings object: " + key)
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(profile: str, config: str | None = None) -> dict:
    if profile not in {"demo", "esp32", "radxa"}:
        raise ValueError("Unknown profile")
    base = yaml.safe_load((ROOT / "profiles/default.yaml").read_text())
    settings = merge(base, yaml.safe_load((ROOT / ("profiles/" + profile + ".yaml")).read_text()) or {})
    if config:
        settings = merge(settings, yaml.safe_load(Path(config).read_text()) or {})
    settings["profile"] = profile
    settings["arm"] = False
    if settings["lease_ms"] < 50 or settings["lease_ms"] > 500:
        raise ValueError("lease_ms must be in 50..500")
    if not 0 < settings["speed_percent"] <= 60:
        raise ValueError("speed_percent must be in 1..60")
    return settings


def get_token(data: Path) -> str:
    data.mkdir(parents=True, exist_ok=True)
    token = os.getenv("M10_CONTROL_TOKEN", "").strip()
    if token:
        return token
    path = data / "control-token"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    token = secrets.token_urlsafe(32)
    with os.fdopen(fd, "w") as handle:
        handle.write(token + "\n")
    return token
