#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root_dir/logs" "$root_dir/data"
nohup python3 "$root_dir/web/server.py" --host 0.0.0.0 --port 8080 > "$root_dir/logs/web.log" 2>&1 &
echo $! > "$root_dir/logs/web.pid"
sleep 1
if ! kill -0 "$(tr -d '[:space:]' < "$root_dir/logs/web.pid")" 2>/dev/null; then echo "M10 web failed to start" >&2; tail -20 "$root_dir/logs/web.log" >&2; exit 1; fi
echo "M10 web started"
echo "PAIRING_TOKEN=$(tr -d '[:space:]' < "$root_dir/data/access-token")"
