#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_USER="${SUDO_USER:-$USER}"

if [[ ! -x "$PROJECT_DIR/run_deadlock_collector_cycle.sh" ]]; then
  echo "Collector runner is not executable under $PROJECT_DIR" >&2
  echo "Run ./deploy/deadlock-collector/install_on_pi.sh before installing the timer." >&2
  exit 1
fi

if [[ ! -x "$PROJECT_DIR/venv/bin/python" ]] && ! command -v python3 >/dev/null 2>&1; then
  echo "No usable Python found. Run ./deploy/deadlock-collector/install_on_pi.sh first." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SERVICE_NAME="deadlock-match-collector"
SERVICE_TEMPLATE="$PROJECT_DIR/deploy/deadlock-collector/systemd/${SERVICE_NAME}.service"
TIMER_TEMPLATE="$PROJECT_DIR/deploy/deadlock-collector/systemd/${SERVICE_NAME}.timer"
TMP_SERVICE="$TMP_DIR/${SERVICE_NAME}.service"
TMP_TIMER="$TMP_DIR/${SERVICE_NAME}.timer"

sed \
  -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
  -e "s|__RUN_USER__|$RUN_USER|g" \
  "$SERVICE_TEMPLATE" > "$TMP_SERVICE"

cp "$TIMER_TEMPLATE" "$TMP_TIMER"

sudo install -m 644 "$TMP_SERVICE" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo install -m 644 "$TMP_TIMER" "/etc/systemd/system/${SERVICE_NAME}.timer"

sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.timer"

echo "Installed ${SERVICE_NAME} systemd timer"
echo "Check status with:"
echo "  sudo systemctl status ${SERVICE_NAME}.timer"
echo "  sudo journalctl -u ${SERVICE_NAME}.service -n 100 --no-pager"
