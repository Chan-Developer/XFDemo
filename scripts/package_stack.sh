#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_DIR="${OUTPUT_DIR:-${PROJECT_DIR}/deploy}"

mkdir -p "${DEPLOY_DIR}"

docker build -t xf-frontend:latest -f "${PROJECT_DIR}/deploy/Dockerfile.frontend" "${PROJECT_DIR}"
docker build -t xf-backend:latest -f "${PROJECT_DIR}/deploy/Dockerfile.backend" "${PROJECT_DIR}"

docker save -o "${DEPLOY_DIR}/xf-frontend-latest.tar" xf-frontend:latest
docker save -o "${DEPLOY_DIR}/xf-backend-latest.tar" xf-backend:latest

# Keep compose/env templates in deploy/ and copy to runtime names.
# When OUTPUT_DIR is the default deploy/ folder, avoid copying compose onto itself.
STACK_DIR="${PROJECT_DIR}/deploy"
if [[ "${DEPLOY_DIR}" != "${STACK_DIR}" ]]; then
  cp "${STACK_DIR}/docker-compose.yml" "${DEPLOY_DIR}/docker-compose.yml"
  cp "${STACK_DIR}/.env.deploy" "${DEPLOY_DIR}/.env"
  cp "${STACK_DIR}/prompt.py" "${DEPLOY_DIR}/prompt.py"
else
  cp "${STACK_DIR}/.env.deploy" "${STACK_DIR}/.env"
fi

printf 'Frontend image: %s\n' "${DEPLOY_DIR}/xf-frontend-latest.tar"
printf 'Backend image: %s\n' "${DEPLOY_DIR}/xf-backend-latest.tar"
printf 'Compose file: %s\n' "${DEPLOY_DIR}/docker-compose.yml"
printf 'Env file: %s\n' "${DEPLOY_DIR}/.env"
