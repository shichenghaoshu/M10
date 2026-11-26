#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"; temp_dir="$(mktemp -d /tmp/m10-camera-npu.XXXXXX)"
adb root >/dev/null; adb wait-for-device
adb shell 'v4l2-ctl -d /dev/video9 --set-fmt-video=width=1280,height=720,pixelformat=MJPG --set-parm=30 --stream-mmap=4 --stream-count=1 --stream-to=/data/local/tmp/m10-live.jpg'
adb pull /data/local/tmp/m10-live.jpg "$temp_dir/live.jpg" >/dev/null
sips -z 300 300 -s format bmp "$temp_dir/live.jpg" --out "$temp_dir/live.bmp" >/dev/null
adb push "$temp_dir/live.bmp" /data/local/tmp/m10-vision/model/live.bmp >/dev/null
adb shell 'cd /data/local/tmp/m10-vision && LD_LIBRARY_PATH=/vendor/lib64 ./bin/m10_rknn_probe ./model/ssd_inception_v2_rknn_1.0.0.rknn ./model/live.bmp 3'

