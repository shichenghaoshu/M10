#!/usr/bin/env bash
set -euo pipefail

FACE_URL="${M10_FACE_UI_URL:-http://127.0.0.1:8765}"
BROWSER=""
for candidate in chromium-browser chromium google-chrome; do
  if command -v "$candidate" >/dev/null 2>&1; then
    BROWSER="$candidate"
    break
  fi
done

if [[ -z "$BROWSER" ]]; then
  echo "未找到 Chromium/Chrome，无法启动全屏表情界面" >&2
  exit 1
fi

if command -v xset >/dev/null 2>&1; then
  xset s off || true
  xset -dpms || true
  xset s noblank || true
fi

exec "$BROWSER" \
  --kiosk \
  --app="$FACE_URL" \
  --autoplay-policy=no-user-gesture-required \
  --disable-session-crashed-bubble \
  --disable-infobars \
  --no-first-run \
  --check-for-update-interval=31536000
