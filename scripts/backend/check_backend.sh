#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_FILE="$ROOT/runtime/logs/backend_runtime.log"

echo "== health =="
curl -fsS http://127.0.0.1:5000/health

if [[ -n "${AUTH_TOKEN:-}" ]]; then
  echo
  echo "== protected endpoints =="
  curl -fsS \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    'http://127.0.0.1:5000/history/inspections?page=1&page_size=1'
  echo
  curl -fsS \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    'http://127.0.0.1:5000/monitor/inspection-stats?limit=5'
else
  echo
  echo "Protected endpoint checks skipped (set AUTH_TOKEN to enable)."
fi

echo
echo "== recent log =="
tail -n 40 "$LOG_FILE"
