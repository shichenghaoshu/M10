#!/usr/bin/env bash
set -euo pipefail
adb get-state >/dev/null
adb root >/dev/null
adb wait-for-device
adb shell 'getprop ro.product.model; getprop ro.product.cpu.abi; getprop ro.build.version.release; uname -a; id'
adb shell 'cat /sys/module/rknpu/version 2>/dev/null || true; strings /vendor/lib64/librknnrt.so 2>/dev/null | grep "librknnrt version" | head -1 || true'
adb shell 'lsusb; for f in /sys/class/video4linux/video*/name; do printf "%s: " "$f"; cat "$f"; done'
adb shell 'dumpsys media.camera | head -80'

