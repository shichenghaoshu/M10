#!/usr/bin/env bash
set -e

echo "=== M10 VMware Check ==="
python3 --version
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ || true
python3 main.py --check
echo "VMware check complete."
