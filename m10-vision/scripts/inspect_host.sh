#!/usr/bin/env bash
set -euo pipefail
uname -a
sw_vers 2>/dev/null || true
python3 --version
cmake --version 2>/dev/null || true
git --version
adb version 2>/dev/null || true
adb devices -l 2>/dev/null || true
docker info --format '{{.ServerVersion}} {{.Architecture}}' 2>/dev/null || true

