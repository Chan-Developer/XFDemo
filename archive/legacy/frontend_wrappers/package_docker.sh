#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Deprecated: packaging has been centralized under /scripts + /deploy.
ROOT_DIR="$(cd "${PROJECT_DIR}/.." && pwd)"
exec "${ROOT_DIR}/scripts/package_stack.sh"
