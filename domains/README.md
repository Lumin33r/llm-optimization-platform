# domains/

Domain configuration files for fine-tuning data organization. Defines data splits, sources, and metadata for domain-specific LoRA fine-tuning.

## Files

| File         | Purpose                                     |
| ------------ | ------------------------------------------- |
| `legal.yaml` | Legal domain configuration for finetune team |

## Schema

```yaml
domain_id: legal
team: finetune
splits:
  train: 0.7              # 70% for training
  eval_holdout: 0.2        # 20% for evaluation
  canary_never_train: 0.1  # 10% held out (never trained on, used for A/B)
sources:
  - path: s3://data-engine/domains/legal/contracts.jsonl
  - path: s3://data-engine/domains/legal/clauses.jsonl
metadata:
  jurisdiction: ["US", "UK", "EU"]
  document_type: ["contract", "brief", "statute"]
```

## Relationship to Other Components

- **finetune-api** serves LoRA models fine-tuned on these domains
- **scripts/finetune-ab-test.sh** uses the `canary_never_train` split for unbiased A/B testing
- **data/promptsets/finetune-domain/** contains domain-specific test prompts
