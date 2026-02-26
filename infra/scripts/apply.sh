#!/bin/bash
set -euo pipefail

ENV="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="${SCRIPT_DIR}/../envs/${ENV}"

if [ ! -d "${ENV_DIR}" ]; then
  echo "Error: Environment directory not found: ${ENV_DIR}"
  exit 1
fi

PLAN_FILE="${ENV_DIR}/tfplan"

if [ ! -f "${PLAN_FILE}" ]; then
  echo "Error: No plan file found. Run plan.sh first."
  exit 1
fi

echo "==> Applying terraform plan for environment: ${ENV}"
cd "${ENV_DIR}"
terraform apply tfplan

echo "==> Apply complete!"
echo "==> Updating kubeconfig..."
aws eks update-kubeconfig \
  --name "$(terraform output -raw eks_cluster_name)" \
  --region "$(terraform output -raw eks_cluster_endpoint | grep -oP '(?<=\.)[a-z]+-[a-z]+-[0-9]+' | head -1 || echo 'us-west-2')"

echo "==> Done! Verify with: kubectl get nodes"
