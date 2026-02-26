#!/bin/bash
set -euo pipefail

ENV="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="${SCRIPT_DIR}/../envs/${ENV}"

if [ ! -d "${ENV_DIR}" ]; then
  echo "Error: Environment directory not found: ${ENV_DIR}"
  exit 1
fi

echo "WARNING: This will destroy ALL infrastructure in the '${ENV}' environment!"
echo ""
read -p "Type the environment name to confirm (${ENV}): " CONFIRM

if [ "${CONFIRM}" != "${ENV}" ]; then
  echo "Confirmation failed. Aborting."
  exit 1
fi

echo "==> Destroying terraform resources for environment: ${ENV}"
cd "${ENV_DIR}"
terraform destroy -var-file=terraform.tfvars

echo "==> Destroy complete for environment: ${ENV}"
