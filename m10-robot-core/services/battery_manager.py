from __future__ import annotations

from pathlib import Path


class BatteryManager:
    def __init__(self, logger) -> None:
        self.logger = logger

    def get_status(self) -> dict:
        candidates = list(Path("/sys/class/power_supply").glob("BAT*"))
        if not candidates:
            return {"status": "unknown", "reason": "battery_device_not_found"}

        battery_dir = candidates[0]
        try:
            capacity = (battery_dir / "capacity").read_text(encoding="utf-8").strip()
            state = (battery_dir / "status").read_text(encoding="utf-8").strip()
            return {"status": "available", "capacity_percent": int(capacity), "charging_state": state}
        except PermissionError:
            return {"status": "error", "reason": "permission_denied"}
        except Exception as exc:
            self.logger.exception("Failed to read battery data")
            return {"status": "error", "reason": "read_failed", "details": str(exc)}
