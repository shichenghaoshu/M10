from __future__ import annotations

import subprocess
from pathlib import Path


class AudioService:
    def __init__(self, config: dict, logger, base_path: Path, input_status: dict | None = None, output_status: dict | None = None) -> None:
        self.config = config
        self.logger = logger
        self.base_path = base_path
        self.initial_input_status = input_status or {}
        self.initial_output_status = output_status or {}

    def _run(self, command: list[str]) -> tuple[int, str, str, str | None]:
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            return completed.returncode, completed.stdout.strip(), completed.stderr.strip(), None
        except FileNotFoundError:
            return 127, "", "", "command_not_found"
        except PermissionError:
            return 126, "", "", "permission_denied"

    def _status_from_command(self, command: list[str], no_device_reason: str) -> dict:
        code, stdout, stderr, error = self._run(command)
        if error == "permission_denied":
            return {"status": "error", "reason": "permission_denied"}
        if error == "command_not_found":
            return {"status": "unavailable", "reason": f"{command[0]}_not_found"}
        output = "\n".join(part for part in [stdout, stderr] if part)
        if code != 0 or "no soundcards found" in output.lower() or "no sound cards found" in output.lower():
            return {"status": "unavailable", "reason": no_device_reason, "details": output}
        return {"status": "available", "details": output}

    def check_input(self) -> dict:
        return self._status_from_command(["arecord", "-l"], "arecord_no_device")

    def check_output(self) -> dict:
        return self._status_from_command(["aplay", "-l"], "aplay_no_device")

    def run_audio_test(self) -> dict:
        if not self.config.get("enabled", True):
            return {"ok": False, "status": "unavailable", "reason": "audio_disabled"}

        input_status = self.check_input()
        output_status = self.check_output()
        if input_status["status"] != "available" or output_status["status"] != "available":
            return {"ok": False, "input": input_status, "output": output_status}

        test_wav = self.base_path / self.config.get("test_wav_path", "data/test.wav")
        test_wav.parent.mkdir(parents=True, exist_ok=True)
        seconds = str(int(self.config.get("record_seconds", 3)))

        record_code, _, record_err, record_error = self._run(["arecord", "-d", seconds, "-f", "cd", "-t", "wav", str(test_wav)])
        if record_error == "permission_denied":
            return {"ok": False, "status": "error", "reason": "permission_denied"}
        if record_code != 0:
            return {"ok": False, "status": "error", "reason": "record_failed", "details": record_err}

        play_code, _, play_err, play_error = self._run(["aplay", str(test_wav)])
        if play_error == "permission_denied":
            return {"ok": False, "status": "error", "reason": "permission_denied"}
        if play_code != 0:
            return {"ok": False, "status": "error", "reason": "playback_failed", "details": play_err}

        return {
            "ok": True,
            "status": "available",
            "record_path": test_wav.relative_to(self.base_path).as_posix(),
        }
