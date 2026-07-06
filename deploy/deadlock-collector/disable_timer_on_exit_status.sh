#!/usr/bin/env bash
set -euo pipefail

TIMER_UNIT="${1:?timer unit is required}"
shift
DISABLE_EXIT_STATUSES=("$@")

if [[ "${#DISABLE_EXIT_STATUSES[@]}" -eq 0 ]]; then
  DISABLE_EXIT_STATUSES=(75)
fi

for disable_status in "${DISABLE_EXIT_STATUSES[@]}"; do
  if [[ "${EXIT_STATUS:-}" == "$disable_status" ]]; then
    echo "Deadlock collector exit status ${EXIT_STATUS}; disabling ${TIMER_UNIT}"
    systemctl disable --now "$TIMER_UNIT"
    exit 0
  fi
done

exit 0
