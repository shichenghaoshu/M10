#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

DEFAULT_OUTPUT = "screen_test.png"


def detect_resolution() -> str:
    if not os.environ.get("DISPLAY"):
        return "headless"

    try:
        result = subprocess.run(
            ["xrandr", "--current"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return "display-present"

    for line in result.stdout.splitlines():
        if " current " in line:
            chunk = line.split(" current ", 1)[1]
            return chunk.split(",", 1)[0].strip()
    return "display-present"


def render_png(output_path: Path, resolution: str) -> None:
    image = Image.new("RGB", (800, 480), color=(18, 34, 52))
    draw = ImageDraw.Draw(image)
    lines = [
        "M10 Screen Test",
        f"Resolution: {resolution}",
        "Status: PASS placeholder",
    ]
    y = 120
    for line in lines:
        draw.text((60, y), line, fill=(240, 240, 240))
        y += 60
    image.save(output_path)


def show_tk_window(resolution: str) -> bool:
    if not os.environ.get("DISPLAY"):
        return False

    try:
        import tkinter as tk
    except Exception:
        return False

    root = tk.Tk()
    root.title("M10 Screen Test")
    root.geometry("480x240")

    labels = [
        "M10 Screen Test",
        f"Resolution: {resolution}",
        "Status: PASS placeholder",
    ]
    for text in labels:
        label = tk.Label(root, text=text, font=("Arial", 16))
        label.pack(pady=10)

    root.after(3000, root.destroy)
    root.mainloop()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Simple screen validation helper.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="PNG output path for headless mode")
    args = parser.parse_args()

    resolution = detect_resolution()
    output_path = Path(args.output)

    render_png(output_path, resolution)
    print(f"Generated {output_path} with resolution marker: {resolution}")

    if show_tk_window(resolution):
        print("Displayed a temporary test window.")
    else:
        print("No graphical desktop detected. PNG output only.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
