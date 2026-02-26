#!/bin/bash
# scripts/validate-autoscaling.sh

echo "=== Autoscaling Validation ==="

# 1. Baseline state
echo "[1/4] Recording baseline..."
BASELINE_REPLICAS=$(kubectl -n llm-baseline get deploy/mistral-7b-instruct-vllm -o jsonpath='{.spec.replicas}')
echo "Baseline replicas: $BASELINE_REPLICAS"

# 2. Generate load
echo "[2/4] Generating load (performance promptset, 50 concurrent)..."
python harness.py \
  --promptset s3://llmplatform-data-engine/promptsets/performance/v1/promptset.jsonl \
  --gateway http://mistral-7b-baseline.llm-baseline.svc:8000 \
  --concurrency 50 \
  --run-id "autoscale-test-$(date +%s)" &

LOAD_PID=$!
sleep 120  # Wait 2 minutes for scaling

# 3. Check scale-up
echo "[3/4] Checking scale-up..."
SCALED_REPLICAS=$(kubectl -n llm-baseline get deploy/mistral-7b-instruct-vllm -o jsonpath='{.status.replicas}')
echo "Scaled replicas: $SCALED_REPLICAS"

if [ "$SCALED_REPLICAS" -gt "$BASELINE_REPLICAS" ]; then
  echo "✓ Scale-up successful"
else
  echo "✗ Scale-up did not occur"
fi

# 4. Stop load and check scale-down
echo "[4/4] Stopping load, waiting for scale-down..."
kill $LOAD_PID 2>/dev/null
sleep 360  # Wait 6 minutes (cooldown + scale-down)

FINAL_REPLICAS=$(kubectl -n llm-baseline get deploy/mistral-7b-instruct-vllm -o jsonpath='{.status.replicas}')
echo "Final replicas: $FINAL_REPLICAS"

if [ "$FINAL_REPLICAS" -le "$BASELINE_REPLICAS" ]; then
  echo "✓ Scale-down successful"
else
  echo "✗ Scale-down did not complete"
fi

echo "=== Autoscaling Validation Complete ==="
