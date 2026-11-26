#!/usr/bin/env bash
set -euo pipefail

uname -a
python3 --version
ip addr
lsusb
ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyS* 2>/dev/null || true
ls /dev/video* 2>/dev/null || true
arecord -l || true
aplay -l || true
df -h
python3 main.py --check
