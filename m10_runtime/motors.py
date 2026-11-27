from __future__ import annotations

import atexit
import importlib.util

from .protocol import V2Link, STOP, ESTOP, CLEAR_ESTOP
from .settings import UPSTREAM

ACTIONS = {"forward", "backward", "left", "right", "stop"}


def load_upstream(name: str):
    spec = importlib.util.spec_from_file_location("m10_dreamupers_" + name, UPSTREAM / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Motor:
    def __init__(self, settings, serial_factory=None):
        self.settings = settings
        self.kind = settings["profile"]
        self.device = None
        self.serial_factory = serial_factory
        self.healthy = False
        self.last_error = None
        self.targets = (0, 0)

    def connect(self):
        self.close()
        self.last_error = None
        if self.kind == "demo":
            self.healthy = True
            return
        if not self.settings["arm"]:
            raise RuntimeError("Hardware is disarmed; use --arm after checking wiring")
        try:
            if self.kind == "esp32":
                self.device = V2Link(self.settings["serial_port"], self.settings["baudrate"],
                                     self.settings["ack_timeout_ms"], self.serial_factory)
                self.device.connect()
            else:
                driver = load_upstream("motor").TB6612MotorDriver
                self.device = driver(**self.settings["gpio"], speed=0)
                atexit.unregister(self.device.cleanup)
                self.device.stop()
            self.healthy = True
        except Exception as exc:
            self.last_error = str(exc)
            self.healthy = False
            raise

    def command(self, action: str, speed_percent: int, duration_ms: int):
        if not isinstance(action, str) or action not in ACTIONS:
            raise ValueError("Unknown action")
        if not self.healthy:
            raise RuntimeError(self.last_error or "Motor not ready")
        speed = int(speed_percent * 10)
        targets = {"forward": (speed, speed), "backward": (-speed, -speed),
                   "left": (-speed, speed), "right": (speed, -speed), "stop": (0, 0)}[action]
        if self.kind == "esp32":
            if action == "stop":
                self.device.exchange(STOP)
            else:
                self.device.set_targets(*targets, duration_ms)
        elif self.kind == "radxa":
            if action != "stop":
                self.device.set_speed(speed_percent / 100)
            getattr(self.device, action)()
        self.targets = targets

    def emergency(self):
        if self.kind == "esp32" and self.device:
            self.device.exchange(ESTOP)
            self.targets = (0, 0)
        else:
            self.command("stop", 0, 1)

    def clear_emergency(self):
        if self.kind == "esp32":
            self.device.exchange(CLEAR_ESTOP)

    def status(self):
        return {"backend": self.kind, "simulated": self.kind == "demo", "ready": self.healthy,
                "armed": self.settings["arm"], "last_error": self.last_error,
                "left_target": self.targets[0], "right_target": self.targets[1],
                "telemetry": self.device.telemetry if isinstance(self.device, V2Link) else None}

    def close(self):
        device = self.device
        self.device = None
        self.healthy = False
        self.targets = (0, 0)
        if device:
            try:
                if isinstance(device, V2Link):
                    try:
                        if device.healthy:
                            device.exchange(STOP)
                    finally:
                        device.close()
                else:
                    device.cleanup()
            except Exception:
                raise
