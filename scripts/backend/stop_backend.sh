#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PID_FILE="$ROOT/runtime/pids/backend.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "backend not running"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "backend stopped: $PID"
else
  echo "stale pid removed: $PID"
fi
rm -f "$PID_FILE"
