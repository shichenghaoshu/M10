#!/usr/bin/env bash
set -euo pipefail
duration_s="${1:-60}"
fps="${M10_CAMERA_FPS:-30}"
frames=$((duration_s * fps))
device="${M10_CAMERA_DEVICE:-/dev/video9}"
adb root >/dev/null
adb wait-for-device
adb shell "v4l2-ctl -d '$device' --set-fmt-video=width=1280,height=720,pixelformat=MJPG --set-parm='$fps' --stream-mmap=4 --stream-count='$frames' --stream-to=/dev/null --stream-poll"

