#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
pid_file="$root_dir/logs/web.pid"
if [[ -f "$pid_file" ]]; then pid=$(tr -d '[:space:]' < "$pid_file"); [[ "$pid" =~ ^[0-9]+$ ]] && kill "$pid" 2>/dev/null || true; fi
adb shell 'pkill -f m10_rknn_probe 2>/dev/null || true' 2>/dev/null || true
echo "M10 services stopped"

