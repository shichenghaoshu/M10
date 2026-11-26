#!/usr/bin/env bash
set -u

echo "[system] uname -a"
uname -a
echo

echo "[python] python3 --version"
python3 --version
echo

echo "[network] ip addr"
ip addr
echo

echo "[usb] lsusb"
lsusb
echo

echo "[serial] ls /dev/ttyUSB* /dev/ttyACM*"
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "No USB serial devices found."
echo

echo "[camera] ls /dev/video*"
ls /dev/video* 2>/dev/null || echo "No video devices found."
echo

echo "[audio-in] arecord -l"
arecord -l || echo "No recording devices reported."
echo

echo "[audio-out] aplay -l"
aplay -l || echo "No playback devices reported."
