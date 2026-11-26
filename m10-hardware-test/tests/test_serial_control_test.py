import importlib.util
from pathlib import Path


def load_serial_control_test():
    script = Path(__file__).resolve().parents[1] / "rk3566" / "serial_control_test.py"
    spec = importlib.util.spec_from_file_location("serial_control_test", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_manual_serial_tool_accepts_firmware_commands():
    module = load_serial_control_test()

    assert module.VALID_COMMANDS == (
        "forward",
        "backward",
        "left",
        "right",
        "stop",
        "status",
        "heartbeat",
    )
