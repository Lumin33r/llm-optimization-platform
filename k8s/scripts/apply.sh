#!/usr/bin/env bash
set -euo pipefail

# apply.sh - Apply Kustomize overlay to the cluster
#
# Usage: ./apply.sh [dev|staging|prod]

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
echo " Applying k8s overlay: ${ENVIRONMENT}"
echo " Directory: ${OVERLAY_DIR}"
echo "============================================"

# Step 1: Apply namespaces first (ensures they exist before other resources)
echo ""
echo "[1/3] Applying namespaces..."
kubectl apply -k "${K8S_DIR}/base/" --selector='kind=Namespace' --prune=false
echo "Namespaces applied."

# Step 2: Preview the diff
echo ""
echo "[2/3] Previewing changes..."
kubectl diff -k "$OVERLAY_DIR" || true

# Step 3: Apply the full overlay
echo ""
echo "[3/3] Applying overlay: ${ENVIRONMENT}..."
kubectl apply -k "$OVERLAY_DIR"

echo ""
echo "============================================"
echo " Apply complete for: ${ENVIRONMENT}"
echo "============================================"

# Verify deployments
echo ""
echo "Deployment status:"
kubectl get deployments -A -l app.kubernetes.io/part-of=llm-optimization-platform

echo ""
echo "Pod status:"
kubectl get pods -A -l app.kubernetes.io/part-of=llm-optimization-platform
