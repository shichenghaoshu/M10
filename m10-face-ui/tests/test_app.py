import asyncio

import pytest

from app import FaceController, extract_server_command, normalize_state


@pytest.mark.parametrize(
    "value,expected",
    [
        (1, "idle_blink"),
        ("10", "low_battery"),
        ("happy", "happy"),
        ("battery-low", "low_battery"),
        ("9.mp4", "thinking"),
        ("聆听", "listening"),
    ],
)
def test_normalize_state(value, expected):
    assert normalize_state(value).key == expected


@pytest.mark.parametrize("value", [0, 11, "missing", True])
def test_rejects_invalid_state(value):
    with pytest.raises(ValueError):
        normalize_state(value)


def test_extracts_nested_server_shapes():
    assert extract_server_command({"data": {"expression": "happy", "duration_ms": 900}}) == {
        "state": "happy",
        "duration_ms": 900,
        "transition_ms": 140,
    }


def test_server_numeric_values_are_sanitized():
    assert extract_server_command({"state": 4, "duration_ms": "4000", "transition_ms": 9000}) == {
        "state": 4,
        "duration_ms": 4000,
        "transition_ms": 2000,
    }


def test_temporary_state_returns_to_default():
    async def scenario():
        face_controller = FaceController(1)
        await face_controller.set_state(4, duration_ms=10)
        assert face_controller.current_state.id == 4
        await asyncio.sleep(0.03)
        assert face_controller.current_state.id == 1

    asyncio.run(scenario())
