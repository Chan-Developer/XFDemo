#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$ROOT"

if [[ ! -f deploy/.env.auth ]]; then
  echo "Missing deploy/.env.auth. Create it from deploy/.env.auth.example first."
  exit 1
fi

docker compose \
  --env-file deploy/.env.auth \
  -f deploy/docker-compose.auth-db.yml \
  up -d

docker compose \
  --env-file deploy/.env.auth \
  -f deploy/docker-compose.auth-db.yml \
  ps
