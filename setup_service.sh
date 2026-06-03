#!/usr/bin/env bash
# Sets up a systemd service for the telegram-to-youtube pipeline.
# Run once from the project root on the Oracle VM:
#   bash setup_service.sh

set -euo pipefail

SERVICE_NAME="tg2yt"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# ── Resolve paths relative to this script ─────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
CURRENT_USER="$(whoami)"

# ── Sanity checks ──────────────────────────────────────────────────────────────
if [[ ! -f "${PYTHON_BIN}" ]]; then
    echo "ERROR: Virtual environment not found at ${SCRIPT_DIR}/.venv"
    echo "       Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/main.py" ]]; then
    echo "ERROR: main.py not found in ${SCRIPT_DIR}"
    echo "       Run this script from the project root directory."
    exit 1
fi

echo "Installing systemd service: ${SERVICE_NAME}"
echo "  Project dir : ${SCRIPT_DIR}"
echo "  Python      : ${PYTHON_BIN}"
echo "  User        : ${CURRENT_USER}"
echo ""

# ── Write unit file ────────────────────────────────────────────────────────────
sudo tee "${SERVICE_FILE}" > /dev/null <<EOF
[Unit]
Description=Telegram → YouTube pipeline
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${PYTHON_BIN} main.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
# Give the network a moment after boot before starting
ExecStartPre=/bin/sleep 5

[Install]
WantedBy=multi-user.target
EOF

# ── Enable and start ───────────────────────────────────────────────────────────
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

# ── Verify ────────────────────────────────────────────────────────────────────
sleep 2
STATUS="$(sudo systemctl is-active "${SERVICE_NAME}")"

echo ""
if [[ "${STATUS}" == "active" ]]; then
    echo "Service is running."
else
    echo "WARNING: Service status is '${STATUS}' — check logs below."
fi

# ── Cron job for health_check.py (every 6 hours) ──────────────────────────────
HEALTH_CMD="${PYTHON_BIN} ${SCRIPT_DIR}/health_check.py >> ${SCRIPT_DIR}/data/health_check.log 2>&1"
CRON_ENTRY="0 */6 * * * ${HEALTH_CMD}"

# Add only if not already present
if crontab -l 2>/dev/null | grep -qF "health_check.py"; then
    echo "Health check cron already installed — skipping."
else
    ( crontab -l 2>/dev/null; echo "${CRON_ENTRY}" ) | crontab -
    echo "Health check cron installed (runs every 6 hours)."
fi

echo ""
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}        # current status"
echo "  sudo journalctl -u ${SERVICE_NAME} -f        # live log tail"
echo "  sudo systemctl stop ${SERVICE_NAME}          # stop"
echo "  sudo systemctl restart ${SERVICE_NAME}       # restart"
echo "  sudo systemctl disable ${SERVICE_NAME}       # remove from autostart"
echo "  crontab -l                                   # view scheduled jobs"
