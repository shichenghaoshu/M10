from __future__ import annotations

from enum import Enum


class RobotState(str, Enum):
    BOOTING = "BOOTING"
    IDLE = "IDLE"
    MANUAL_CONTROL = "MANUAL_CONTROL"
    MOVING = "MOVING"
    VIDEO_ACTIVE = "VIDEO_ACTIVE"
    LOW_BATTERY = "LOW_BATTERY"
    FAULT = "FAULT"
    SHUTDOWN = "SHUTDOWN"


class StateMachine:
    def __init__(self) -> None:
        self.state = RobotState.BOOTING
        self.reason = "startup"
        self.fault: dict | None = None
        self.esp32_connected = False
        self.battery = {"status": "unknown", "reason": "battery_status_not_set"}
        self.obstacle = {"status": "unknown", "reason": "obstacle_status_not_set"}

    def set_state(self, new_state: RobotState | str, reason: str = "") -> None:
        self.state = RobotState(new_state)
        self.reason = reason

    def get_state(self) -> dict:
        return {"state": self.state.value, "reason": self.reason, "fault": self.fault}

    def set_fault(self, error_code: str, message: str) -> None:
        self.fault = {"error_code": error_code, "message": message}
        self.set_state(RobotState.FAULT, reason=message)

    def clear_fault(self) -> None:
        self.fault = None
        if self.state == RobotState.FAULT:
            self.set_state(RobotState.IDLE, reason="fault_cleared")

    def update_esp32(self, connected: bool) -> None:
        self.esp32_connected = connected

    def update_battery(self, battery_status: dict) -> None:
        self.battery = battery_status

    def update_obstacle(self, obstacle_status: dict) -> None:
        self.obstacle = obstacle_status

    def get_safety_report(self) -> dict:
        blockers: list[str] = []
        if self.state == RobotState.FAULT or self.fault:
            blockers.append("fault_active")
        if not self.esp32_connected:
            blockers.append("esp32_not_connected")
        if self.battery.get("status") == "available" and self.battery.get("capacity_percent", 100) <= 5:
            blockers.append("critical_battery")
        obstacle_state = self.obstacle.get("status")
        if obstacle_state == "available" and self.obstacle.get("distance_mm") is not None:
            if int(self.obstacle["distance_mm"]) <= int(self.obstacle.get("stop_distance_mm", 250)):
                blockers.append("obstacle_detected")
        return {"safe_to_move": not blockers, "blockers": blockers}

    def is_safe_to_move(self) -> bool:
        return self.get_safety_report()["safe_to_move"]
