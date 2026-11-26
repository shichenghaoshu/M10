from __future__ import annotations

import fcntl
import glob
import os
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


FACE_STYLES = {
    "idle": ("M10 Idle", (65, 90, 119)),
    "happy": ("M10 Happy", (52, 120, 80)),
    "moving": ("M10 Moving", (44, 92, 160)),
    "low_battery": ("M10 Low Battery", (140, 95, 42)),
    "error": ("M10 Error", (140, 48, 48)),
    "sleep": ("M10 Sleep", (76, 67, 118)),
}


class DisplayService:
    def __init__(self, config: dict, logger, base_path: Path, discovery_status: dict | None = None) -> None:
        self.config = config
        self.logger = logger
        self.base_path = base_path
        self.discovery_status = discovery_status or {}
        self.environment = dict(os.environ)

    @staticmethod
    def _available_status(**payload):
        return {"status": "available", **payload}

    @staticmethod
    def _preview_only_status(**payload):
        return {"status": "preview_only", **payload}

    @staticmethod
    def _error_status(reason: str, **payload):
        return {"status": "error", "reason": reason, **payload}

    def check_display(self) -> dict:
        if not self.config.get("enabled", True):
            return {"status": "unavailable", "reason": "display_disabled"}

        if self.environment.get("DISPLAY"):
            resolution = None
            try:
                result = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, check=False)
                for line in result.stdout.splitlines():
                    if " current " in line:
                        resolution = line.split(" current ", 1)[1].split(",", 1)[0].strip()
                        break
            except FileNotFoundError:
                pass
            return {"status": "available", "backend": "x11", "resolution": resolution}

        if self.environment.get("WAYLAND_DISPLAY"):
            return {"status": "available", "backend": "wayland"}

        fb_devices = sorted(glob.glob("/dev/fb*"))
        if fb_devices:
            return {"status": "available", "backend": "fbdev", "devices": fb_devices}

        return {"status": "unavailable", "reason": "display_environment_not_found"}

    def _build_preview_image(self, headline: str, subtitle: str) -> Image.Image:
        return Image.new(
            "RGB",
            (int(self.config.get("width", 480)), int(self.config.get("height", 320))),
            color=(28, 33, 44),
        )

    def _render_preview(self, headline: str, subtitle: str) -> tuple[Image.Image, str]:
        preview_path = self.base_path / self.config.get("preview_path", "data/display_preview.png")
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        image = self._build_preview_image(headline, subtitle)
        draw = ImageDraw.Draw(image)
        draw.rectangle((16, 16, image.width - 16, image.height - 16), outline=(255, 255, 255), width=2)
        draw.text((40, 80), headline, fill=(255, 255, 255))
        draw.text((40, 140), subtitle, fill=(220, 220, 220))
        image.save(preview_path)
        return image, preview_path.relative_to(self.base_path).as_posix()

    def _get_fbdev_device(self, display_status: dict) -> str | None:
        devices = []
        if display_status.get("backend") == "fbdev":
            devices.extend(display_status.get("devices", []))

        discovered = self.discovery_status.get("devices", [])
        devices.extend(discovered)
        devices.extend(sorted(glob.glob("/dev/fb*")))

        for device in devices:
            if device:
                return device
        return None

    def _load_fbdev_info(self, framebuffer) -> tuple[dict, dict]:
        fix_fmt = "@16sL4I3HIL2I3H"
        var_fmt = "@40I"
        fix_buffer = bytearray(struct.calcsize(fix_fmt))
        var_buffer = bytearray(struct.calcsize(var_fmt))
        fcntl.ioctl(framebuffer.fileno(), 0x4602, fix_buffer, True)
        fcntl.ioctl(framebuffer.fileno(), 0x4600, var_buffer, True)

        fix_values = struct.unpack(fix_fmt, fix_buffer)
        var_values = struct.unpack(var_fmt, var_buffer)

        fix_info = {
            "id": fix_values[0].split(b"\x00", 1)[0].decode(errors="ignore"),
            "smem_len": fix_values[2],
            "line_length": fix_values[9],
        }
        var_info = {
            "xres": var_values[0],
            "yres": var_values[1],
            "xres_virtual": var_values[2],
            "yres_virtual": var_values[3],
            "xoffset": var_values[4],
            "yoffset": var_values[5],
            "bits_per_pixel": var_values[6],
            "red": {"offset": var_values[8], "length": var_values[9], "msb_right": var_values[10]},
            "green": {"offset": var_values[11], "length": var_values[12], "msb_right": var_values[13]},
            "blue": {"offset": var_values[14], "length": var_values[15], "msb_right": var_values[16]},
            "transp": {"offset": var_values[17], "length": var_values[18], "msb_right": var_values[19]},
        }
        return fix_info, var_info

    @staticmethod
    def _scale_channel(value: int, length: int) -> int:
        if length <= 0:
            return 0
        max_value = (1 << length) - 1
        return int(round((value / 255) * max_value))

    def _pack_pixel(self, red: int, green: int, blue: int, alpha: int, var_info: dict, bytes_per_pixel: int) -> bytes:
        pixel_value = 0
        for channel_name, channel_value in (
            ("red", red),
            ("green", green),
            ("blue", blue),
            ("transp", alpha),
        ):
            bitfield = var_info[channel_name]
            if bitfield["msb_right"]:
                raise ValueError("msb_right_pixel_formats_not_supported")
            scaled = self._scale_channel(channel_value, bitfield["length"])
            pixel_value |= scaled << bitfield["offset"]
        return pixel_value.to_bytes(bytes_per_pixel, byteorder=sys.byteorder, signed=False)

    def _write_image_to_fbdev(self, image: Image.Image, device: str) -> dict:
        try:
            with open(device, "r+b", buffering=0) as framebuffer:
                fix_info, var_info = self._load_fbdev_info(framebuffer)
                bits_per_pixel = int(var_info["bits_per_pixel"])
                if bits_per_pixel % 8 != 0:
                    return self._error_status("framebuffer_unsupported_pixel_format", device=device, bits_per_pixel=bits_per_pixel)

                bytes_per_pixel = bits_per_pixel // 8
                rendered = image.convert("RGBA").resize((int(var_info["xres"]), int(var_info["yres"])))
                line_length = int(fix_info["line_length"])
                xoffset = int(var_info["xoffset"])
                yoffset = int(var_info["yoffset"])
                yres = int(var_info["yres"])
                frame_height = max(yres + yoffset, int(var_info["yres_virtual"]) or 0, yres)
                frame_size = max(line_length * frame_height, int(fix_info["smem_len"]) or 0)
                frame_bytes = bytearray(frame_size)

                for y in range(rendered.height):
                    row_start = (y + yoffset) * line_length + (xoffset * bytes_per_pixel)
                    for x in range(rendered.width):
                        pixel_start = row_start + (x * bytes_per_pixel)
                        frame_bytes[pixel_start : pixel_start + bytes_per_pixel] = self._pack_pixel(
                            *rendered.getpixel((x, y)),
                            var_info=var_info,
                            bytes_per_pixel=bytes_per_pixel,
                        )

                framebuffer.seek(0)
                framebuffer.write(frame_bytes)
                framebuffer.flush()
        except PermissionError:
            return self._error_status("permission_denied", device=device)
        except OSError as exc:
            self.logger.exception("Framebuffer write failed for %s", device)
            return self._error_status("framebuffer_write_failed", device=device, details=str(exc))
        except ValueError as exc:
            return self._error_status(str(exc), device=device)

        return self._available_status(backend="fbdev", device=device, resolution=f"{rendered.width}x{rendered.height}")

    def generate_preview(self, face_name: str) -> dict:
        label, _ = FACE_STYLES.get(face_name, FACE_STYLES["error"])
        _, path = self._render_preview(label, "preview_only")
        return {"status": "preview_only", "path": path, "face_name": face_name}

    def show_face(self, face_name: str) -> dict:
        if face_name not in FACE_STYLES:
            return {"status": "error", "reason": "invalid_face_name"}
        display_status = self.check_display()
        label, _ = FACE_STYLES[face_name]
        preview_image, preview_path = self._render_preview(label, display_status.get("backend", "preview_only"))

        if display_status["status"] != "available":
            return self._preview_only_status(reason=display_status["reason"], path=preview_path, face_name=face_name)

        if display_status["backend"] == "fbdev":
            device = self._get_fbdev_device(display_status)
            if not device:
                return self._preview_only_status(reason="framebuffer_device_not_found", path=preview_path, face_name=face_name)
            fb_result = self._write_image_to_fbdev(preview_image, device)
            return {**fb_result, "path": preview_path, "face_name": face_name}

        if display_status["backend"] != "x11":
            return self._preview_only_status(
                reason=f"{display_status['backend']}_renderer_not_implemented",
                path=preview_path,
                face_name=face_name,
            )

        try:
            import tkinter as tk
        except Exception:
            return {"status": "error", "reason": "tkinter_not_available", "path": preview_path}

        try:
            root = tk.Tk()
            root.title("M10 Display Test")
            root.geometry(f"{self.config.get('width', 480)}x{self.config.get('height', 320)}")
            label_widget = tk.Label(root, text=label, font=("Arial", 24))
            label_widget.pack(expand=True)
            root.update()
            root.after(750, root.destroy)
            root.mainloop()
            return {"status": "available", "backend": "x11", "path": preview_path, "face_name": face_name}
        except Exception as exc:
            self.logger.exception("Display face render failed")
            return {"status": "error", "reason": "display_render_failed", "details": str(exc), "path": preview_path}

    def show_text(self, text: str) -> dict:
        display_status = self.check_display()
        preview_image, preview_path = self._render_preview("M10 Text", text)
        if display_status["status"] != "available":
            return self._preview_only_status(reason=display_status["reason"], path=preview_path, text=text)
        if display_status["backend"] == "fbdev":
            device = self._get_fbdev_device(display_status)
            if not device:
                return self._preview_only_status(reason="framebuffer_device_not_found", path=preview_path, text=text)
            fb_result = self._write_image_to_fbdev(preview_image, device)
            return {**fb_result, "path": preview_path, "text": text}
        if display_status["backend"] != "x11":
            return self._preview_only_status(
                reason=f"{display_status['backend']}_renderer_not_implemented",
                path=preview_path,
                text=text,
            )

        try:
            import tkinter as tk
        except Exception:
            return {"status": "error", "reason": "tkinter_not_available", "path": preview_path}

        try:
            root = tk.Tk()
            root.title("M10 Display Text")
            root.geometry(f"{self.config.get('width', 480)}x{self.config.get('height', 320)}")
            label_widget = tk.Label(root, text=text, font=("Arial", 20), wraplength=int(self.config.get("width", 480)) - 40)
            label_widget.pack(expand=True, padx=20, pady=20)
            root.update()
            root.after(750, root.destroy)
            root.mainloop()
            return {"status": "available", "backend": "x11", "path": preview_path, "text": text}
        except Exception as exc:
            self.logger.exception("Display text render failed")
            return {"status": "error", "reason": "display_render_failed", "details": str(exc), "path": preview_path}
