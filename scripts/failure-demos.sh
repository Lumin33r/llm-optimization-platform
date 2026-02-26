#!/bin/bash
# scripts/failure-demos.sh

set -e

echo "=== Controlled Failure Demonstration ==="

# 1. Readiness-Gated Traffic
echo "[1/3] Deploying slow-startup service..."
kubectl apply -f k8s/quant/deployment-slow-startup.yaml
echo "Watch Grafana: Traffic should drop to Ready pods only"
echo "Expected: No 5xx errors, traffic gates correctly"
sleep 70  # Wait for startup
kubectl delete -f k8s/quant/deployment-slow-startup.yaml

# 2. Quota Rejection
echo "[2/3] Testing quota rejection..."
kubectl apply -f k8s/quant/resourcequota-tight.yaml
kubectl apply -f k8s/quant/deployment-exceeds-quota.yaml || true
echo "Watch Grafana: Pods should be Pending, no traffic shift"
sleep 30
kubectl delete -f k8s/quant/deployment-exceeds-quota.yaml || true
kubectl delete -f k8s/quant/resourcequota-tight.yaml

# 3. SageMaker Timeout
echo "[3/3] Testing timeout propagation..."
python harness.py \
  --promptset s3://llmplatform-data-engine/promptsets/performance/v1/long-only.jsonl \
  --team quant \
  --run-id "timeout-demo-$(date +%s)" \
  --concurrency 5
echo "Watch Grafana: 504s from FastAPI, SageMaker latency normal"

echo "=== Failure Demonstration Complete ==="
echo "Review Grafana dashboards for observability validation"
