#!/usr/bin/env bash
set -euo pipefail

ROOT="/data/clj/Project/XFDemo"
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
