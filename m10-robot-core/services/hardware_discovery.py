from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    error_reason: str | None = None


class HardwareDiscovery:
    def __init__(
        self,
        config: dict,
        logger,
        environment: dict[str, str] | None = None,
        command_runner: Callable[[list[str]], CommandResult] | None = None,
        path_exists: Callable[[str], bool] | None = None,
        globber: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.environment = environment or dict(os.environ)
        self.command_runner = command_runner or self._run_command
        self.path_exists = path_exists or (lambda path: Path(path).exists())
        self.globber = globber or glob.glob

    def _run_command(self, command: list[str]) -> CommandResult:
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
            return CommandResult(
                returncode=completed.returncode,
                stdout=completed.stdout.strip(),
                stderr=completed.stderr.strip(),
            )
        except FileNotFoundError:
            return CommandResult(returncode=127, stdout="", stderr="", error_reason="command_not_found")
        except PermissionError:
            return CommandResult(returncode=126, stdout="", stderr="", error_reason="permission_denied")

    @staticmethod
    def _available_status(**payload):
        return {"status": "available", **payload}

    @staticmethod
    def _unavailable_status(reason: str, **payload):
        return {"status": "unavailable", "reason": reason, **payload}

    @staticmethod
    def _error_status(reason: str, **payload):
        return {"status": "error", "reason": reason, **payload}

    def _collect_paths(self, exact_paths: list[str], patterns: list[str]) -> list[str]:
        found = {path for path in exact_paths if self.path_exists(path)}
        for pattern in patterns:
            found.update(self.globber(pattern))
        return sorted(found)

    def discover_serial(self) -> dict:
        serial_config = self.config.get("serial", {})
        devices = self._collect_paths(
            serial_config.get("port_candidates", []),
            ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*"],
        )
        if not devices:
            return self._unavailable_status("device_not_found")
        return self._available_status(devices=devices)

    def discover_camera(self) -> dict:
        video_config = self.config.get("video", {})
        devices = self._collect_paths(
            video_config.get("device_candidates", []),
            ["/dev/video*"],
        )
        if not devices:
            return self._unavailable_status("no_/dev/video_device_found")
        return self._available_status(devices=devices)

    def _detect_audio_device(self, command: list[str], no_device_reason: str) -> dict:
        result = self.command_runner(command)
        if result.error_reason == "permission_denied":
            return self._error_status("permission_denied")
        if result.error_reason == "command_not_found":
            return self._unavailable_status(f"{command[0]}_not_found")

        output = "\n".join(part for part in [result.stdout, result.stderr] if part)
        lower_output = output.lower()
        if result.returncode != 0 or "no soundcards found" in lower_output or "no sound cards found" in lower_output:
            return self._unavailable_status(no_device_reason, details=output or "")
        return self._available_status(details=output)

    def discover_audio_input(self) -> dict:
        return self._detect_audio_device(["arecord", "-l"], "arecord_no_device")

    def discover_audio_output(self) -> dict:
        return self._detect_audio_device(["aplay", "-l"], "aplay_no_device")

    def discover_display(self) -> dict:
        if self.environment.get("DISPLAY"):
            resolution = None
            xrandr = self.command_runner(["xrandr", "--current"])
            if xrandr.returncode == 0 and xrandr.stdout:
                for line in xrandr.stdout.splitlines():
                    if " current " in line:
                        resolution = line.split(" current ", 1)[1].split(",", 1)[0].strip()
                        break
            return self._available_status(backend="x11", resolution=resolution)

        if self.environment.get("WAYLAND_DISPLAY"):
            return self._available_status(backend="wayland")

        fb_devices = sorted(self.globber("/dev/fb*"))
        if fb_devices:
            return self._available_status(backend="fbdev", devices=fb_devices)

        return self._unavailable_status("display_environment_not_found")

    def discover_usb_devices(self) -> dict:
        result = self.command_runner(["lsusb"])
        if result.error_reason == "permission_denied":
            return self._error_status("permission_denied")
        if result.error_reason == "command_not_found":
            return self._unavailable_status("lsusb_not_found")
        if result.returncode != 0:
            return self._error_status("lsusb_failed", details=result.stderr or result.stdout)
        return self._available_status(details=result.stdout)

    def discover_system_info(self) -> dict:
        disk_usage = shutil.disk_usage("/")
        return {
            "status": "available",
            "platform": platform.platform(),
            "uname": " ".join(platform.uname()),
            "python_version": sys.version.split()[0],
            "disk_total_gb": round(disk_usage.total / 1024 / 1024 / 1024, 2),
            "disk_free_gb": round(disk_usage.free / 1024 / 1024 / 1024, 2),
        }

    def run_full_discovery(self) -> dict:
        discovery = {
            "serial": self.discover_serial(),
            "camera": self.discover_camera(),
            "audio_input": self.discover_audio_input(),
            "audio_output": self.discover_audio_output(),
            "display": self.discover_display(),
            "usb": self.discover_usb_devices(),
            "system": self.discover_system_info(),
        }
        self.logger.info("Hardware discovery results: %s", discovery)
        return discovery
