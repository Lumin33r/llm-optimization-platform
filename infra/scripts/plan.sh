#!/bin/bash
set -euo pipefail

ENV="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="${SCRIPT_DIR}/../envs/${ENV}"

if [ ! -d "${ENV_DIR}" ]; then
  echo "Error: Environment directory not found: ${ENV_DIR}"
  exit 1
fi

echo "==> Running terraform plan for environment: ${ENV}"
cd "${ENV_DIR}"
terraform plan -out=tfplan -var-file=terraform.tfvars
echo "==> Plan saved to ${ENV_DIR}/tfplan"
