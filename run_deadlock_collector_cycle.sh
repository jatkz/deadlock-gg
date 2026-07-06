#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -a
  # Strip Windows CRLF line endings while sourcing, without rewriting secrets.
  # shellcheck disable=SC1090
  source <(sed 's/\r$//' "$SCRIPT_DIR/.env")
  set +a
fi

if [[ -x "$SCRIPT_DIR/venv/bin/python" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "python3 is not installed on this system." >&2
  exit 1
fi

mkdir -p "${DEADLOCK_DATA_DIR:-data/deadlock-ranked}"

LOCK_FILE="${DEADLOCK_DATA_DIR:-data/deadlock-ranked}/.deadlock_match_collector.lock"
exec 9>"$LOCK_FILE"
if command -v flock >/dev/null 2>&1; then
  if ! flock -n 9; then
    echo "[$(date --iso-8601=seconds)] Deadlock match collector already running; skipping this cycle"
    exit 0
  fi
else
  echo "flock is not installed; collector overlap protection is disabled" >&2
fi

echo "[$(date --iso-8601=seconds)] Starting Deadlock match collector cycle"
set +e
"$PYTHON_BIN" scripts/deadlock_match_collector.py "$@"
STATUS=$?
set -e

if [[ "$STATUS" -eq 75 ]]; then
  echo "[$(date --iso-8601=seconds)] Deadlock collector reached the saved-match cap"
elif [[ "$STATUS" -eq 0 ]]; then
  echo "[$(date --iso-8601=seconds)] Deadlock match collector cycle complete"
else
  echo "[$(date --iso-8601=seconds)] Deadlock match collector failed with status $STATUS" >&2
fi

exit "$STATUS"
