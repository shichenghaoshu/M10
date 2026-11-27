import pytest

from m10_runtime.control import Control
from m10_runtime.motors import Motor
from m10_runtime.settings import load_settings


def controller():
    motor = Motor(load_settings("demo"))
    motor.connect()
    clock = [10.0]
    return Control(motor, lease_ms=250, clock=lambda: clock[0]), clock


def test_deadline_stops_without_a_status_or_client_message():
    control, clock = controller()
    control.command("forward", "owner")
    clock[0] += 0.251
    control.tick()
    assert control.status()["action"] == "stop"
    assert control.motor.targets == (0, 0)


def test_other_controller_cannot_take_lease_or_stop_on_disconnect():
    control, clock = controller()
    control.command("left", "one")
    with pytest.raises(RuntimeError):
        control.command("right", "two")
    control.disconnected("two")
    assert control.action == "left"
    control.disconnected("one")
    assert control.action == "stop"


def test_lease_can_transfer_only_after_expiry():
    control, clock = controller()
    control.command("forward", "one")
    clock[0] += 0.3
    control.command("right", "two")
    assert control.owner == "two" and control.motor.targets == (200, -200)


def test_estop_requires_explicit_clear():
    control, _ = controller()
    control.command("forward", "one")
    control.emergency()
    with pytest.raises(RuntimeError):
        control.command("forward", "one")
    control.clear_emergency()
    assert control.command("left", "one")["action"] == "left"


@pytest.mark.parametrize("bad", [None, {}, [], "fly"])
def test_malformed_commands_never_reach_driver(bad):
    control, _ = controller()
    with pytest.raises(ValueError):
        control.command(bad, "one")
    assert control.motor.targets == (0, 0)


def test_disarmed_hardware_does_not_silently_become_demo():
    motor = Motor(load_settings("esp32"))
    with pytest.raises(RuntimeError, match="disarmed"):
        motor.connect()
    assert not motor.healthy and not motor.status()["simulated"]


def test_motion_failure_requests_stop_and_blocks_further_motion():
    control, _ = controller()
    calls = []
    def broken(action, speed, duration):
        calls.append(action)
        if action != "stop":
            raise OSError("driver fault")
    control.motor.command = broken
    with pytest.raises(OSError):
        control.command("forward", "one")
    assert calls == ["forward", "stop"]
    assert not control.motor.healthy and control.owner is None


def test_radxa_executes_the_original_driver_with_injected_gpio(monkeypatch):
    import sys
    import types
    class Line:
        value = 0
        def request(self, **kwargs): pass
        def set_value(self, value): self.value = value
    class Chip:
        OPEN_BY_NUMBER = 1
        def __init__(self, *args): pass
        def get_line(self, number): return Line()
        def close(self): pass
    class PWM:
        def __init__(self, *args): self.duty_cycle = 0
        def enable(self): pass
        def disable(self): pass
    gpio = types.ModuleType("gpiod")
    gpio.Chip, gpio.LINE_REQ_DIR_OUT = Chip, 1
    periphery = types.ModuleType("periphery")
    periphery.PWM = PWM
    monkeypatch.setitem(sys.modules, "gpiod", gpio)
    monkeypatch.setitem(sys.modules, "periphery", periphery)
    settings = load_settings("radxa")
    settings["arm"] = True
    motor = Motor(settings)
    motor.connect()
    motor.command("left", 20, 250)
    assert motor.device.ain1.value == 0 and motor.device.ain2.value == 1
    assert motor.device.bin1.value == 1 and motor.device.bin2.value == 0
    assert motor.device.pwm_a.duty_cycle == 0.2
    motor.close()
