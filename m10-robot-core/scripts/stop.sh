#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f data/m10_robot_core.pid ]]; then
  echo "No PID file found."
  exit 0
fi

PID="$(cat data/m10_robot_core.pid)"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped PID $PID"
else
  echo "Process $PID is not running."
fi

rm -f data/m10_robot_core.pid
