#!/usr/bin/env bash
set -euo pipefail

ROOT="/data/clj/Project/XFDemo"
LOG_FILE="$ROOT/runtime/logs/backend_runtime.log"

echo "== health =="
curl -sS http://127.0.0.1:5000/health

echo
echo "== history =="
curl -sS 'http://127.0.0.1:5000/history/inspections?page=1&page_size=1'

echo
echo "== monitor =="
curl -sS 'http://127.0.0.1:5000/monitor/inspection-stats?limit=5'

echo
echo "== recent log =="
tail -n 40 "$LOG_FILE"
