#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_DIR="${OUTPUT_DIR:-${PROJECT_DIR}/output/deploy/images}"
STACK_DIR="${PROJECT_DIR}/deploy"

mkdir -p "${IMAGE_DIR}"

docker build -t xf-frontend:latest -f "${PROJECT_DIR}/deploy/Dockerfile.frontend" "${PROJECT_DIR}"
docker build -t xf-backend:latest -f "${PROJECT_DIR}/deploy/Dockerfile.backend" "${PROJECT_DIR}"

docker save -o "${IMAGE_DIR}/xf-frontend-latest.tar" xf-frontend:latest
docker save -o "${IMAGE_DIR}/xf-backend-latest.tar" xf-backend:latest

printf 'Frontend image: %s\n' "${IMAGE_DIR}/xf-frontend-latest.tar"
printf 'Backend image: %s\n' "${IMAGE_DIR}/xf-backend-latest.tar"
printf 'Compose file: %s\n' "${STACK_DIR}/docker-compose.yml"
printf 'Env template: %s\n' "${STACK_DIR}/.env.deploy"
