from __future__ import annotations

from services.state_machine import RobotState, StateMachine


def test_fault_blocks_motion():
    machine = StateMachine()
    machine.update_esp32(True)
    machine.set_fault("serial_failure", "ESP32 missing")
    assert machine.state == RobotState.FAULT
    assert machine.is_safe_to_move() is False


def test_disconnected_esp32_blocks_motion():
    machine = StateMachine()
    machine.update_esp32(False)
    assert machine.is_safe_to_move() is False
    assert "esp32_not_connected" in machine.get_safety_report()["blockers"]


def test_unknown_battery_does_not_fake_critical_state():
    machine = StateMachine()
    machine.update_esp32(True)
    machine.update_battery({"status": "unknown", "reason": "battery_device_not_found"})
    assert machine.is_safe_to_move() is True


def test_obstacle_blocks_motion_when_distance_is_too_small():
    machine = StateMachine()
    machine.update_esp32(True)
    machine.update_obstacle({"status": "available", "distance_mm": 100, "stop_distance_mm": 250})
    assert machine.is_safe_to_move() is False
