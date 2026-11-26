from __future__ import annotations


class HealthMonitor:
    def __init__(self, logger) -> None:
        self.logger = logger

    def build_report(self, hardware: dict, battery: dict, sensors: dict, state: dict) -> dict:
        unavailable = [name for name, section in hardware.items() if isinstance(section, dict) and section.get("status") == "unavailable"]
        errors = [name for name, section in hardware.items() if isinstance(section, dict) and section.get("status") == "error"]
        return {
            "status": "ok" if not errors else "degraded",
            "unavailable_components": unavailable,
            "error_components": errors,
            "battery": battery,
            "sensors": sensors,
            "state": state,
        }
