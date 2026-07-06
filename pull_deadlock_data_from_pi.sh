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

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

SSH_TARGET="${1:-${DEADLOCK_PI_SSH:-}}"
REMOTE_DIR="${DEADLOCK_PI_REMOTE_DATA_DIR:-}"
if [[ -z "$REMOTE_DIR" ]]; then
  REMOTE_DIR='~/deadlock_gg_collector/data/deadlock-ranked'
fi
if [[ "$REMOTE_DIR" == "$HOME/deadlock_gg_collector/data/deadlock-ranked" ]]; then
  REMOTE_DIR='~/deadlock_gg_collector/data/deadlock-ranked'
fi
LOCAL_DIR="${DEADLOCK_PI_LOCAL_DATA_DIR:-data/deadlock-ranked-pi}"

if [[ -z "$SSH_TARGET" ]]; then
  echo "Usage: $0 [--dry-run] pi@raspberrypi.local" >&2
  echo "Or set DEADLOCK_PI_SSH in .env." >&2
  exit 2
fi

mkdir -p "$LOCAL_DIR"

echo "Remote: $SSH_TARGET:$REMOTE_DIR"
echo "Local:  $LOCAL_DIR"

if command -v rsync >/dev/null 2>&1; then
  RSYNC_ARGS=(-av --progress)
  if [[ "$DRY_RUN" -eq 1 ]]; then
    RSYNC_ARGS+=(--dry-run)
  fi
  rsync "${RSYNC_ARGS[@]}" "$SSH_TARGET:$REMOTE_DIR/" "$LOCAL_DIR/"
else
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "rsync is not installed; dry-run fallback would copy with ssh + tar."
    exit 0
  fi
  ssh "$SSH_TARGET" "cd $REMOTE_DIR && tar -czf - ." | tar -C "$LOCAL_DIR" -xzf -
fi
