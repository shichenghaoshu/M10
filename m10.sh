#!/usr/bin/env bash
set -euo pipefail
m10_root="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON:-python3}" "$m10_root/m10_runtime/bootstrap.py" "$@"
