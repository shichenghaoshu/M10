#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
target=/data/local/tmp/m10-vision
adb root >/dev/null; adb wait-for-device
adb shell "mkdir -p $target/bin $target/model"
adb push "$root_dir/build/android/install/bin/m10_rknn_probe" "$target/bin/"
adb push "$root_dir/models/ssd_inception_v2_rknn_1.0.0.rknn" "$target/model/"
adb push "$root_dir/models/road.bmp" "$target/model/"
adb push "$root_dir/models/box_priors.txt" "$target/model/"
adb push "$root_dir/models/coco_labels_list.txt" "$target/model/"
adb shell "chmod 755 $target/bin/m10_rknn_probe"
