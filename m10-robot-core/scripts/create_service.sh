#!/usr/bin/env bash
set -euo pipefail

SERVICE_FILE="m10-robot-core.service"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=M10 Robot Core
After=network.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
ExecStart=/usr/bin/python3 ${PROJECT_DIR}/main.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "Created ${SERVICE_FILE} in $(pwd)"
