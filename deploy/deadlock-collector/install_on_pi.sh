#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is not installed on this system." >&2
  exit 1
fi

rm -rf venv
if ! python3 -m venv venv; then
  echo >&2
  echo "Failed to create the virtual environment." >&2
  if [[ -f /etc/debian_version ]]; then
    echo "On Raspberry Pi OS / Debian, install the venv package with:" >&2
    echo "  sudo apt-get update" >&2
    echo "  sudo apt-get install -y python3-venv" >&2
  fi
  echo "Then rerun ./deploy/deadlock-collector/install_on_pi.sh" >&2
  exit 1
fi

chmod +x run_deadlock_collector_cycle.sh pull_deadlock_data_from_pi.sh
chmod +x scripts/deadlock_match_collector.py
mkdir -p data/deadlock-ranked

for env_file in .env .env.example; do
  if [[ -f "$env_file" ]]; then
    sed -i 's/\r$//' "$env_file"
  fi
done

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Adjust Deadlock filters before starting timers."
fi

echo
echo "Install complete."
echo "Test with:"
echo "  ./run_deadlock_collector_cycle.sh --dry-run"
echo
echo "Then install the systemd timer with:"
echo "  ./deploy/deadlock-collector/install_systemd.sh"
