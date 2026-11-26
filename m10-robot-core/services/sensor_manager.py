from __future__ import annotations


class SensorManager:
    def __init__(self, logger) -> None:
        self.logger = logger

    def get_status(self) -> dict:
        return {
            "obstacle": {"status": "unknown", "reason": "sensor_not_configured"},
            "tof": {"status": "unknown", "reason": "sensor_not_configured"},
        }
