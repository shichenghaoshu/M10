#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"; stamp=$(date +%Y%m%d-%H%M%S); out="$root_dir/logs/collect-$stamp"; mkdir -p "$out"
adb exec-out logcat -d > "$out/android-logcat.txt" 2>/dev/null || true
adb exec-out dumpsys media.camera > "$out/media-camera.txt" 2>/dev/null || true
adb exec-out sh -c 'cat /sys/module/rknpu/version; cat /sys/class/devfreq/fde40000.npu/cur_freq' > "$out/npu.txt" 2>/dev/null || true
echo "$out"

