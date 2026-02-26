#!/usr/bin/env bash
set -euo pipefail

# diff.sh - Preview changes before applying
#
# Usage: ./diff.sh [dev|staging|prod]

ENVIRONMENT="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(dirname "$SCRIPT_DIR")"
OVERLAY_DIR="${K8S_DIR}/overlays/${ENVIRONMENT}"

if [[ ! -d "$OVERLAY_DIR" ]]; then
  echo "ERROR: Overlay directory not found: ${OVERLAY_DIR}"
  echo "Available environments: dev, staging, prod"
  exit 1
fi

echo "============================================"
echo " Diff for overlay: ${ENVIRONMENT}"
echo " Directory: ${OVERLAY_DIR}"
echo "============================================"
echo ""

# Show the rendered manifests
echo "--- Rendered manifests ---"
kubectl kustomize "$OVERLAY_DIR"

echo ""
echo "--- Diff against live cluster ---"
kubectl diff -k "$OVERLAY_DIR" || true
