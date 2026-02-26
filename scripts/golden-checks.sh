#!/bin/bash
# scripts/golden-checks.sh

set -e

echo "=== vLLM Baseline Golden Checks ==="

# 1. Rollout status
echo "[1/4] Checking rollout status..."
kubectl -n llm-baseline rollout status deploy/mistral-7b-instruct-vllm --timeout=10m

# 2. Model list endpoint
echo "[2/4] Checking /v1/models..."
kubectl -n llm-baseline port-forward svc/mistral-7b-baseline 8000:8000 &
PF_PID=$!
sleep 3

MODELS=$(curl -sf http://localhost:8000/v1/models)
echo "$MODELS" | jq -e '.data[0].id' > /dev/null
echo "✓ Model available: $(echo $MODELS | jq -r '.data[0].id')"

# 3. Chat completions
echo "[3/4] Testing /v1/chat/completions..."
RESPONSE=$(curl -sf http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "TheBloke/Mistral-7B-Instruct-v0.2-AWQ",
    "messages": [{"role": "user", "content": "Say hello in one word."}],
    "max_tokens": 10
  }')

CONTENT=$(echo "$RESPONSE" | jq -r '.choices[0].message.content')
echo "✓ Response: $CONTENT"

# 4. Metrics endpoint
echo "[4/4] Checking /metrics..."
METRICS=$(curl -sf http://localhost:8000/metrics | head -20)
echo "$METRICS" | grep -q "vllm_" && echo "✓ Prometheus metrics available"

kill $PF_PID 2>/dev/null

echo "=== All Golden Checks Passed ==="
