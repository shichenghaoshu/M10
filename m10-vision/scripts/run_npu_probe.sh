#!/usr/bin/env bash
set -euo pipefail
adb shell 'cd /data/local/tmp/m10-vision && LD_LIBRARY_PATH=/vendor/lib64 ./bin/m10_rknn_probe ./model/ssd_inception_v2_rknn_1.0.0.rknn ./model/road.bmp 20'
