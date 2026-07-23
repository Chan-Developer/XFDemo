#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <user@host> [remote_dir]" >&2
  exit 1
fi

REMOTE_HOST="$1"
REMOTE_DIR="${2:-/data/clj/Project/XFDemo/deploy}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_DIR="${IMAGE_DIR:-${PROJECT_DIR}/output/deploy/images}"
DEPLOY_DIR="${DEPLOY_DIR:-${PROJECT_DIR}/deploy}"

BACKEND_TAR="${IMAGE_DIR}/xf-backend-latest.tar"
FRONTEND_TAR="${IMAGE_DIR}/xf-frontend-latest.tar"
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.yml"
ENV_FILE="${DEPLOY_DIR}/.env"

SSH_OPTS=(-o StrictHostKeyChecking=accept-new)
if [[ -n "${SSH_KEY:-}" ]]; then
  SSH_OPTS+=(-i "${SSH_KEY}")
fi

for file in "${BACKEND_TAR}" "${FRONTEND_TAR}" "${COMPOSE_FILE}" "${ENV_FILE}"; do
  if [[ ! -f "${file}" ]]; then
    echo "Missing required file: ${file}" >&2
    echo "Hint: run 'bash ${PROJECT_DIR}/scripts/package_stack.sh' first." >&2
    exit 1
  fi
done

echo "Uploading deploy bundle to ${REMOTE_HOST}:${REMOTE_DIR}"
ssh "${SSH_OPTS[@]}" "${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}'"
scp "${SSH_OPTS[@]}" \
  "${BACKEND_TAR}" \
  "${FRONTEND_TAR}" \
  "${COMPOSE_FILE}" \
  "${ENV_FILE}" \
  "${REMOTE_HOST}:${REMOTE_DIR}/"

echo "Loading images and starting stack on remote..."
ssh "${SSH_OPTS[@]}" "${REMOTE_HOST}" \
  "cd '${REMOTE_DIR}' && \
   docker load -i '$(basename "${BACKEND_TAR}")' && \
   docker load -i '$(basename "${FRONTEND_TAR}")' && \
   docker compose -f '$(basename "${COMPOSE_FILE}")' up -d"

echo "OK: ${REMOTE_HOST}:${REMOTE_DIR}"
