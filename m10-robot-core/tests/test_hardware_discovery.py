from __future__ import annotations

from services.hardware_discovery import CommandResult, HardwareDiscovery


def test_hardware_discovery_returns_unavailable_without_devices():
    config = {
        "serial": {"port_candidates": ["/dev/ttyUSB0"]},
        "video": {"device_candidates": ["/dev/video0"]},
    }

    def fake_runner(command: list[str]) -> CommandResult:
        if command[0] in {"arecord", "aplay"}:
            return CommandResult(returncode=1, stdout="", stderr="no soundcards found...")
        if command[0] == "lsusb":
            return CommandResult(returncode=0, stdout="Bus 001 Device 001: ID 1d6b:0002 root hub", stderr="")
        if command[0] == "xrandr":
            return CommandResult(returncode=1, stdout="", stderr="Can't open display")
        raise AssertionError(f"Unexpected command: {command}")

    discovery = HardwareDiscovery(
        config=config,
        logger=type("L", (), {"info": lambda *args, **kwargs: None})(),
        environment={},
        command_runner=fake_runner,
        path_exists=lambda path: False,
        globber=lambda pattern: [],
    )
    result = discovery.run_full_discovery()

    assert result["serial"]["status"] == "unavailable"
    assert result["camera"]["status"] == "unavailable"
    assert result["audio_input"]["reason"] == "arecord_no_device"
    assert result["audio_output"]["reason"] == "aplay_no_device"


def test_hardware_discovery_marks_permission_denied():
    config = {"serial": {"port_candidates": []}, "video": {"device_candidates": []}}

    def fake_runner(command: list[str]) -> CommandResult:
        return CommandResult(returncode=126, stdout="", stderr="", error_reason="permission_denied")

    discovery = HardwareDiscovery(
        config=config,
        logger=type("L", (), {"info": lambda *args, **kwargs: None})(),
        command_runner=fake_runner,
    )
    audio_status = discovery.discover_audio_input()
    assert audio_status["status"] == "error"
    assert audio_status["reason"] == "permission_denied"
