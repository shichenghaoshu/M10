from __future__ import annotations

from pathlib import Path

from services.display_service import DisplayService


class DummyLogger:
    def exception(self, *args, **kwargs):
        return None


def build_service(tmp_path: Path) -> DisplayService:
    config = {
        "enabled": True,
        "width": 480,
        "height": 320,
        "preview_path": "data/display_preview.png",
    }
    return DisplayService(
        config=config,
        logger=DummyLogger(),
        base_path=tmp_path,
        discovery_status={"status": "available", "backend": "fbdev", "devices": ["/dev/fb0"]},
    )


def test_pack_pixel_rgb565(tmp_path: Path):
    service = build_service(tmp_path)
    var_info = {
        "red": {"offset": 11, "length": 5, "msb_right": 0},
        "green": {"offset": 5, "length": 6, "msb_right": 0},
        "blue": {"offset": 0, "length": 5, "msb_right": 0},
        "transp": {"offset": 0, "length": 0, "msb_right": 0},
    }

    assert service._pack_pixel(255, 0, 0, 255, var_info, 2) == b"\x00\xf8"
    assert service._pack_pixel(255, 255, 255, 255, var_info, 2) == b"\xff\xff"


def test_show_face_writes_fbdev_when_available(tmp_path: Path):
    service = build_service(tmp_path)
    service.check_display = lambda: {"status": "available", "backend": "fbdev", "devices": ["/dev/fb0"]}
    calls = []

    def fake_write(image, device: str):
        calls.append((image.size, device))
        return {"status": "available", "backend": "fbdev", "device": device, "resolution": "480x320"}

    service._write_image_to_fbdev = fake_write
    result = service.show_face("idle")

    assert result["status"] == "available"
    assert result["backend"] == "fbdev"
    assert result["device"] == "/dev/fb0"
    assert result["face_name"] == "idle"
    assert result["path"] == "data/display_preview.png"
    assert calls == [((480, 320), "/dev/fb0")]
    assert (tmp_path / "data/display_preview.png").exists()


def test_show_text_returns_fbdev_permission_denied(tmp_path: Path):
    service = build_service(tmp_path)
    service.check_display = lambda: {"status": "available", "backend": "fbdev", "devices": ["/dev/fb0"]}
    service._write_image_to_fbdev = lambda image, device: {"status": "error", "reason": "permission_denied", "device": device}

    result = service.show_text("hello rk3566")

    assert result["status"] == "error"
    assert result["reason"] == "permission_denied"
    assert result["device"] == "/dev/fb0"
    assert result["text"] == "hello rk3566"
    assert result["path"] == "data/display_preview.png"


def test_show_face_without_display_returns_preview_only(tmp_path: Path):
    service = build_service(tmp_path)
    service.check_display = lambda: {"status": "unavailable", "reason": "display_environment_not_found"}

    result = service.show_face("happy")

    assert result["status"] == "preview_only"
    assert result["reason"] == "display_environment_not_found"
    assert result["face_name"] == "happy"
    assert result["path"] == "data/display_preview.png"
