#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/collector-dist"
ARCHIVE_PATH="$OUTPUT_DIR/deadlock_collector_pi.tar.gz"
INCLUDE_ENV=0

if [[ "${1:-}" == "--with-env" ]]; then
  INCLUDE_ENV=1
fi

mkdir -p "$OUTPUT_DIR"

FILES=(
  README.md
  docs/deadlock-collector.md
  .env.example
  assets/deadlock/manifest.json
  deadlock_on
  deadlock_off
  deadlock_clean
  deadlock_pull_1000
  scripts/build_deadlock_asset_manifest.py
  scripts/build_deadlock_sqlite_db.py
  scripts/deadlock_match_collector.py
  run_deadlock_collector_cycle.sh
  pull_deadlock_data_from_pi.sh
  deploy/deadlock-collector/install_on_pi.sh
  deploy/deadlock-collector/install_systemd.sh
  deploy/deadlock-collector/disable_timer_on_exit_status.sh
  deploy/deadlock-collector/systemd/deadlock-match-collector.service
  deploy/deadlock-collector/systemd/deadlock-match-collector.timer
)

if [[ "$INCLUDE_ENV" -eq 1 && -f "$SCRIPT_DIR/.env" ]]; then
  FILES+=(.env)
fi

tar -czf "$ARCHIVE_PATH" -C "$SCRIPT_DIR" "${FILES[@]}"
echo "Created $ARCHIVE_PATH"
if [[ "$INCLUDE_ENV" -eq 0 ]]; then
  echo ".env was not included. Copy it separately or rerun with --with-env."
fi
