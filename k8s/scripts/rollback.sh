#!/usr/bin/env bash
set -euo pipefail

# rollback.sh - Rollback a deployment to a previous revision
#
# Usage: ./rollback.sh <deployment> <namespace> [revision]
#
# Examples:
#   ./rollback.sh gateway platform
#   ./rollback.sh gateway platform 2
#   ./rollback.sh quant-api quant

DEPLOYMENT="${1:-}"
NAMESPACE="${2:-}"
REVISION="${3:-}"

if [[ -z "$DEPLOYMENT" || -z "$NAMESPACE" ]]; then
  echo "Usage: $0 <deployment> <namespace> [revision]"
  echo ""
  echo "Examples:"
  echo "  $0 gateway platform        # Rollback to previous revision"
  echo "  $0 gateway platform 2      # Rollback to specific revision"
  echo "  $0 quant-api quant"
  echo "  $0 finetune-api finetune"
  echo "  $0 eval-api eval"
  exit 1
fi

echo "============================================"
echo " Rollback: ${DEPLOYMENT} in ${NAMESPACE}"
echo "============================================"

# Show current rollout history
echo ""
echo "Rollout history:"
kubectl rollout history "deployment/${DEPLOYMENT}" -n "$NAMESPACE"

# Perform rollback
echo ""
if [[ -n "$REVISION" ]]; then
  echo "Rolling back to revision: ${REVISION}..."
  kubectl rollout undo "deployment/${DEPLOYMENT}" -n "$NAMESPACE" --to-revision="$REVISION"
else
  echo "Rolling back to previous revision..."
  kubectl rollout undo "deployment/${DEPLOYMENT}" -n "$NAMESPACE"
fi

# Wait for rollout
echo ""
echo "Waiting for rollout to complete..."
kubectl rollout status "deployment/${DEPLOYMENT}" -n "$NAMESPACE" --timeout=120s

echo ""
echo "============================================"
echo " Rollback complete: ${DEPLOYMENT}"
echo "============================================"

# Show current state
echo ""
echo "Current pods:"
kubectl get pods -n "$NAMESPACE" -l "app=${DEPLOYMENT}"
