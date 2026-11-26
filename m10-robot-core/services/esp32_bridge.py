from __future__ import annotations

import glob
import time
from pathlib import Path

try:
    import serial
    from serial import SerialException
except ImportError:  # pragma: no cover - depends on runtime environment
    serial = None
    SerialException = Exception


class ESP32Bridge:
    def __init__(self, config: dict, logger) -> None:
        self.config = config
        self.logger = logger
        self.serial_handle = None
        self.connected_port: str | None = None
        self.last_status: dict = {"connected": False, "status": "unavailable", "reason": "not_initialized"}

    def _candidate_ports(self) -> list[str]:
        ports = set(self.config.get("port_candidates", []))
        ports.update(glob.glob("/dev/ttyUSB*"))
        ports.update(glob.glob("/dev/ttyACM*"))
        ports.update(glob.glob("/dev/ttyS*"))
        return sorted(port for port in ports if Path(port).exists())

    def connect(self) -> dict:
        if not self.config.get("enabled", True):
            self.last_status = {"connected": False, "status": "unavailable", "reason": "serial_disabled"}
            return self.last_status

        if serial is None:
            self.last_status = {"connected": False, "status": "error", "reason": "pyserial_not_installed"}
            return self.last_status

        if self.serial_handle and self.serial_handle.is_open:
            self.last_status = {
                "connected": True,
                "status": "available",
                "port": self.connected_port,
                "baudrate": self.config.get("baudrate", 115200),
            }
            return self.last_status

        ports = self._candidate_ports()
        if not ports:
            self.last_status = {"connected": False, "status": "unavailable", "reason": "serial_device_not_found"}
            return self.last_status

        for port in ports:
            try:
                handle = serial.Serial(
                    port=port,
                    baudrate=int(self.config.get("baudrate", 115200)),
                    timeout=float(self.config.get("timeout", 1.0)),
                )
                time.sleep(0.2)
                self.serial_handle = handle
                self.connected_port = port
                self.last_status = {"connected": True, "status": "available", "port": port}
                self.logger.info("ESP32 bridge connected to %s", port)
                return self.last_status
            except PermissionError:
                self.logger.exception("Permission denied while opening serial port %s", port)
                self.last_status = {"connected": False, "status": "error", "reason": "permission_denied", "port": port}
                return self.last_status
            except SerialException as exc:
                self.logger.warning("Failed to open serial port %s: %s", port, exc)

        self.last_status = {"connected": False, "status": "error", "reason": "open_failed"}
        return self.last_status

    def disconnect(self) -> dict:
        if self.serial_handle and self.serial_handle.is_open:
            self.serial_handle.close()
        self.serial_handle = None
        self.connected_port = None
        self.last_status = {"connected": False, "status": "unavailable", "reason": "disconnected"}
        return self.last_status

    def is_connected(self) -> bool:
        return bool(self.serial_handle and self.serial_handle.is_open)

    def get_status(self) -> dict:
        if self.is_connected():
            return {"connected": True, "status": "available", "port": self.connected_port}
        return self.last_status

    def send_command(self, cmd: str) -> dict:
        if not self.is_connected():
            connect_result = self.connect()
            if not connect_result.get("connected"):
                return {"ok": False, **connect_result, "command": cmd}

        assert self.serial_handle is not None
        try:
            self.serial_handle.write(f"{cmd}\n".encode("utf-8"))
            self.serial_handle.flush()
            time.sleep(0.1)
            lines: list[str] = []
            deadline = time.time() + float(self.config.get("timeout", 1.0)) + 1.0
            while time.time() < deadline:
                raw = self.serial_handle.readline()
                if not raw:
                    continue
                decoded = raw.decode("utf-8", errors="replace").strip()
                if decoded:
                    lines.append(decoded)
                if self.serial_handle.in_waiting == 0 and lines:
                    break
            return {
                "ok": True,
                "status": "available",
                "command": cmd,
                "response": "\n".join(lines) if lines else "",
                "port": self.connected_port,
            }
        except PermissionError:
            self.logger.exception("Permission denied while writing command %s", cmd)
            return {"ok": False, "status": "error", "reason": "permission_denied", "command": cmd}
        except SerialException as exc:
            self.logger.exception("Serial write failed for command %s", cmd)
            return {"ok": False, "status": "error", "reason": "serial_write_failed", "command": cmd, "details": str(exc)}

    def forward(self) -> dict:
        return self.send_command("forward")

    def backward(self) -> dict:
        return self.send_command("backward")

    def left(self) -> dict:
        return self.send_command("left")

    def right(self) -> dict:
        return self.send_command("right")

    def stop(self) -> dict:
        return self.send_command("stop")

    def status(self) -> dict:
        return self.send_command("status")

    def heartbeat(self) -> dict:
        return self.send_command("heartbeat")
