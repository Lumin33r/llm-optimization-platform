#!/bin/bash
# scripts/quant-comparison.sh

RUN_ID="quant-$(date +%Y%m%d-%H%M%S)"
PROMPTSET="s3://llmplatform-data-engine/promptsets/quant-sensitivity/v1/promptset.jsonl"

# Download promptset
aws s3 cp $PROMPTSET /tmp/promptset.jsonl

# Run against each variant
for VARIANT in fp16 gptq-4bit awq-4bit; do
  echo "Running $VARIANT..."
  python harness.py \
    --promptset /tmp/promptset.jsonl \
    --team quant \
    --variant $VARIANT \
    --run-id "${RUN_ID}-${VARIANT}" \
    --concurrency 20
done

echo "Results: Run ID prefix = $RUN_ID"
