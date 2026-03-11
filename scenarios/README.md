# scenarios/

Test scenario templates that define prompt generation rules. Used by `scripts/generate-promptsets.py` and `scripts/generate-benchmark.py` to create structured promptsets.

## Files

| File               | Purpose                                        |
| ------------------ | ---------------------------------------------- |
| `performance.yaml` | Throughput stress test scenario template        |

## Schema

```yaml
scenario_id: perf_throughput
description: "Throughput stress test"
prompt_templates:
  - template: "Write a {length} summary of {topic}."
    variables:
      length: ["one-sentence", "paragraph", "detailed"]
      topic: ["${domain_topics}"]
    target_output_tokens:
      one-sentence: 50
      paragraph: 200
      detailed: 800
token_rules:
  input_range: [50, 500]
  output_buckets: [50, 200, 800]   # short / medium / long
```

## Relationship to Other Components

- **services/data-engine/generator.py** uses token rules to assign output length buckets
- **scripts/generate-promptsets.py** reads scenarios to generate promptsets
- **data/promptsets/** stores the generated output
