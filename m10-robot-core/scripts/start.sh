#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs data
nohup python3 main.py > logs/runtime.stdout 2>&1 &
echo $! > data/m10_robot_core.pid
echo "M10 Robot Core started with PID $(cat data/m10_robot_core.pid)"
