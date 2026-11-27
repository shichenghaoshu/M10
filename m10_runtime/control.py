from __future__ import annotations

import threading
import time

from .motors import ACTIONS


class Control:
    """Only fresh control messages renew a lease. Status heartbeats never do."""
    def __init__(self, motor, lease_ms=250, speed=20, clock=time.monotonic):
        self.motor, self.clock = motor, clock
        self.lease_ms, self.speed = lease_ms, speed
        self.lock = threading.RLock()
        self.owner = None
        self.expires = 0.0
        self.action = "stop"
        self.estopped = False
        self.error = None

    def _stop(self):
        self.owner = None
        self.expires = 0
        self.action = "stop"
        try:
            self.motor.command("stop", 0, 1)
        except Exception as exc:
            self.error = str(exc)
            self.motor.healthy = False
            raise

    def command(self, action: str, owner: str):
        if not isinstance(action, str) or action not in ACTIONS:
            raise ValueError("Unknown action")
        with self.lock:
            if action == "stop":
                self._stop()
                return self.status()
            if self.estopped:
                raise RuntimeError("Emergency stop is latched")
            now = self.clock()
            if self.owner and self.owner != owner and now < self.expires:
                raise RuntimeError("Another controller owns the active motion lease")
            try:
                self.motor.command(action, self.speed, self.lease_ms)
            except Exception as exc:
                self.error = str(exc)
                self.owner = None
                self.expires = 0
                self.action = "stop"
                try:
                    self.motor.command("stop", 0, 1)
                except Exception:
                    pass
                self.motor.healthy = False
                raise
            self.owner, self.expires, self.action = owner, now + self.lease_ms / 1000, action
            return self.status()

    def tick(self):
        with self.lock:
            if self.owner and self.clock() >= self.expires:
                self._stop()

    def disconnected(self, owner):
        with self.lock:
            if self.owner == owner:
                self._stop()

    def emergency(self):
        with self.lock:
            self.estopped = True
            self.owner, self.expires, self.action = None, 0, "stop"
            self.motor.emergency()
            return self.status()

    def clear_emergency(self):
        with self.lock:
            self._stop()
            self.motor.clear_emergency()
            self.estopped = False
            return self.status()

    def set_speed(self, speed: int):
        if isinstance(speed, bool) or not isinstance(speed, int) or not 1 <= speed <= 60:
            raise ValueError("speed must be an integer in 1..60")
        with self.lock:
            self.speed = speed

    def status(self):
        with self.lock:
            return {"action": self.action, "emergency_latched": self.estopped,
                    "speed_percent": self.speed, "lease_ms": self.lease_ms,
                    "lease_remaining_ms": max(0, int((self.expires - self.clock()) * 1000)),
                    "error": self.error, "motor": self.motor.status()}
