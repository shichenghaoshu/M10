#!/bin/sh
set -eu

if [ "$#" -ne 2 ] || [ "$2" != "--erase-xiaozhi" ]; then
  echo "Usage: $0 /dev/cu.usbserial-PORT --erase-xiaozhi" >&2
  exit 2
fi

M10_FLASH_PORT="$1"
case "$M10_FLASH_PORT" in
  /dev/cu.*|/dev/tty.*) ;;
  *) echo "ERROR: Refusing unexpected serial path: $M10_FLASH_PORT" >&2; exit 2 ;;
esac
if [ ! -c "$M10_FLASH_PORT" ]; then
  echo "ERROR: Serial port is not present: $M10_FLASH_PORT" >&2
  exit 1
fi

M10_REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
M10_IMAGE="$M10_REPO_DIR/output/firmware/m10_motor_controller_n16r8/m10_motor_controller_n16r8_merged.bin"
M10_ESPTOOL="${M10_ESPTOOL:-$(command -v esptool || command -v esptool.py || true)}"
M10_EXPECTED_SHA="1b08b66243dd9cb43b896d03c3eb8b14286be8e5b9f62c74263e3291a823bc45"

if [ ! -x "$M10_ESPTOOL" ]; then
  echo "ERROR: esptool not found: $M10_ESPTOOL" >&2
  exit 1
fi
if [ ! -f "$M10_IMAGE" ]; then
  echo "ERROR: Firmware image not found: $M10_IMAGE" >&2
  exit 1
fi

M10_ACTUAL_SHA=$(shasum -a 256 "$M10_IMAGE" | awk '{print $1}')
if [ "$M10_ACTUAL_SHA" != "$M10_EXPECTED_SHA" ]; then
  echo "ERROR: Firmware SHA-256 mismatch. Rebuild and audit before flashing." >&2
  exit 1
fi

echo "Target: $M10_FLASH_PORT"
echo "Image:  $M10_IMAGE"
echo "SHA256: $M10_ACTUAL_SHA"
echo "This operation erases the complete ESP32-S3 flash, including XiaoZhi."

"$M10_ESPTOOL" --chip esp32s3 --port "$M10_FLASH_PORT" --baud 115200 \
  --before default_reset --after hard_reset write_flash --erase-all --verify \
  --flash_mode dio --flash_freq 80m --flash_size 16MB 0x0 "$M10_IMAGE"
