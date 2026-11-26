#!/usr/bin/env bash
set -u

echo "[audio-in] arecord -l"
arecord -l || echo "No recording devices reported."
echo

echo "[audio-out] aplay -l"
aplay -l || echo "No playback devices reported."
echo

echo "[record] Capturing 3 seconds to test.wav"
if ! arecord -d 3 -f cd -t wav test.wav; then
  echo "ERROR: Failed to record audio to test.wav" >&2
  exit 1
fi

echo "[playback] Playing test.wav"
if ! aplay test.wav; then
  echo "ERROR: Failed to play test.wav" >&2
  exit 1
fi

echo "Audio test completed."
