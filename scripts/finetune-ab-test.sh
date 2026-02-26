#!/bin/bash
# scripts/finetune-ab-test.sh

RUN_ID="ab-$(date +%Y%m%d-%H%M%S)"
DOMAIN="legal"
PROMPTSET="s3://llmplatform-data-engine/promptsets/domain/${DOMAIN}/v1/canary_never_train.jsonl"

aws s3 cp $PROMPTSET /tmp/promptset.jsonl

# Run A/B comparison
python harness.py \
  --promptset /tmp/promptset.jsonl \
  --team finetune \
  --variant lora-legal-v4 \
  --run-id "${RUN_ID}-A"

python harness.py \
  --promptset /tmp/promptset.jsonl \
  --team finetune \
  --variant lora-legal-v5 \
  --run-id "${RUN_ID}-B"

# Compare results
python compare_ab.py --run-a "${RUN_ID}-A" --run-b "${RUN_ID}-B"
