#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PID_FILE="$ROOT/runtime/pids/backend.pid"
LOG_FILE="$ROOT/runtime/logs/backend_runtime.log"
PYTHON_BIN="$ROOT/.venv-langgraph/bin/python"

mkdir -p "$ROOT/runtime/pids" "$ROOT/runtime/logs"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "backend already running: $PID"
    exit 0
  fi
fi

cd "$ROOT"
nohup "$PYTHON_BIN" -m backend.app >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "backend started: $(cat "$PID_FILE")"
