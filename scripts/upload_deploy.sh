#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_DIR="${IMAGE_DIR:-${PROJECT_DIR}/output/deploy/images}"
DEPLOY_DIR="${DEPLOY_DIR:-${PROJECT_DIR}/deploy}"

REMOTE_HOST="${REMOTE_HOST:-root@100.91.118.106}"
REMOTE_DIR="${REMOTE_DIR:-/root/workspace/XFDeploy}"

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
    exit 1
  fi
done

echo "Uploading deploy artifacts to ${REMOTE_HOST}:${REMOTE_DIR}"
ssh "${SSH_OPTS[@]}" "${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}'"
scp "${SSH_OPTS[@]}" \
  "${BACKEND_TAR}" \
  "${FRONTEND_TAR}" \
  "${COMPOSE_FILE}" \
  "${ENV_FILE}" \
  "${REMOTE_HOST}:${REMOTE_DIR}/"

echo "Upload completed:"
echo "  ${BACKEND_TAR##*/}"
echo "  ${FRONTEND_TAR##*/}"
echo "  ${COMPOSE_FILE##*/}"
echo "  ${ENV_FILE##*/}"
