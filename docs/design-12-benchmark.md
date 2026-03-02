# Design Document 12: Benchmark Test Battery

## Overview

The Benchmark Test Battery is a standardized, large-scale test suite that exercises all three team models (quant, finetune, eval) with enough data to produce statistically meaningful comparisons. It generates 700 prompts across 3 team-specific promptsets and can be triggered with a single button from the Grafana Test Harness panel.

**Purpose:**
- Populate team dashboards with sufficient data to show real differences between models
- Provide a reproducible baseline measurement for model quality, latency, and throughput
- Enable before/after comparisons when model configurations change

**Depends On:** [design-09-data-engine.md](design-09-data-engine.md), [design-10-models.md](design-10-models.md), [design-11-team-dashboards.md](design-11-team-dashboards.md)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Grafana Test Harness Panel                  │
│  ┌─────────────┐  ┌──────────────────────────────────┐  │
│  │ Run Harness  │  │  Run Benchmark (orange button)   │  │
│  │ (single team)│  │  → fires all 3 teams at once     │  │
│  └─────────────┘  └──────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────┘
                            │ POST /harness/benchmark
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    Data Engine API                       │
│  _execute_benchmark() runs sequentially:                 │
│    1. quant  → benchmark-quant  (250 prompts)           │
│    2. finetune → benchmark-finetune (250 prompts)       │
│    3. eval   → benchmark-eval   (200 prompts)           │
└───────────────────────────┬─────────────────────────────┘
                            │ via TestHarness
                            ▼
┌─────────────────────────────────────────────────────────┐
│                      Gateway                             │
│  Routes to /api/{team}/predict                           │
│    quant    → vLLM AWQ model (g4dn.xlarge)              │
│    finetune → vLLM LoRA model (g4dn.xlarge)             │
│    eval     → vLLM Judge model (g4dn.xlarge)            │
└─────────────────────────────────────────────────────────┘
```

---

## Benchmark Promptsets

### benchmark-quant (250 prompts)

Tests AWQ quantization quality vs FP16 reference. Designed to expose precision loss from 4-bit quantization.

| Category | Count | Purpose | Expected Contains |
|----------|-------|---------|-------------------|
| math | 50 | Arithmetic precision (multiply, powers, division, percentages) | Exact numerical answers |
| reasoning | 50 | Logic puzzles, word problems, riddles | Key conclusion words |
| code | 50 | Python functions, SQL queries, algorithms | Function signatures, keywords |
| factual | 50 | Verifiable facts (science, history, geography) | Specific fact values |
| long_form | 50 | Extended explanations (500 token max) | None (latency/throughput only) |

### benchmark-finetune (250 prompts)

Tests LoRA domain adaptation vs base model. Includes domain-specific prompts and regression checks.

| Category | Count | Purpose | Expected Contains |
|----------|-------|---------|-------------------|
| medical | 60 | Clinical terminology, pathophysiology, treatment protocols | Medical terms |
| legal | 60 | Legal concepts, procedures, constitutional law | Legal terminology |
| technical | 60 | K8s, AWS, databases, networking, observability | Technical terms |
| regression | 40 | Basic math, geography, science (catch catastrophic forgetting) | Simple factual answers |
| cross_domain | 30 | Questions spanning medical+legal+technical | Multi-domain terms |

### benchmark-eval (200 prompts)

Tests judge model scoring consistency and calibration across response types.

| Category | Count | Purpose | Expected Contains |
|----------|-------|---------|-------------------|
| coherence | 50 | Structured explanations and logical ordering | None (quality measured by judge) |
| helpfulness | 50 | Actionable guides, checklists, comparisons | None |
| factuality | 50 | Verifiable facts requiring accurate recall | Specific fact values |
| edge_case | 50 | Paradoxes, philosophical questions, ambiguity | None/loose |

---

## API Endpoints

### POST /harness/benchmark

Start a full benchmark run across all teams.

**Request:**
```json
{
  "concurrency": 10
}
```

**Response:**
```json
{
  "benchmark_id": "benchmark-20260301-143022-a1b2c3",
  "status": "pending",
  "team_runs": {},
  "team_status": {
    "quant": "pending",
    "finetune": "pending",
    "eval": "pending"
  },
  "started_at": "2026-03-01T14:30:22Z",
  "completed_at": null,
  "summary": null
}
```

### GET /harness/benchmark/{benchmark_id}

Poll benchmark status. Returns aggregated results when complete.

**Response (completed):**
```json
{
  "benchmark_id": "benchmark-20260301-143022-a1b2c3",
  "status": "completed",
  "team_runs": {
    "quant": "bench-quant-a1b2c3",
    "finetune": "bench-finetune-a1b2c3",
    "eval": "bench-eval-a1b2c3"
  },
  "team_status": {
    "quant": "completed",
    "finetune": "completed",
    "eval": "completed"
  },
  "started_at": "2026-03-01T14:30:22Z",
  "completed_at": "2026-03-01T14:45:11Z",
  "summary": {
    "quant": {
      "total": 250,
      "passed": 232,
      "failed": 18,
      "pass_rate": 92.8,
      "avg_latency_ms": 1423.5,
      "avg_tokens_per_second": 28.4,
      "category_breakdown": {
        "math": {"total": 50, "passed": 47},
        "reasoning": {"total": 50, "passed": 43},
        "code": {"total": 50, "passed": 46},
        "factual": {"total": 50, "passed": 48},
        "long_form": {"total": 50, "passed": 48}
      }
    },
    "finetune": { "...": "..." },
    "eval": { "...": "..." }
  }
}
```

---

## UI Integration

The "Run Benchmark" button is located in the Test Harness panel in Grafana, next to the existing "Run Harness" button.

### Visual Design
- **Run Harness** (green) — runs a single promptset against one team
- **Run Benchmark** (orange) — runs all 3 teams with their full benchmark promptsets

### Benchmark Progress Display
- Shows per-team status badges: `quant: running`, `finetune: pending`, `eval: pending`
- Progress counter: "Benchmark 1/3", "Benchmark 2/3", "Benchmark 3/3"
- On completion: summary table with per-team totals, pass rates, latency, tokens/s

### Max Prompts Cap
- Increased from 1000 to 5000 to accommodate benchmark sizes
- Benchmark mode always runs ALL prompts (no cap)

---

## Data Generation

### Script: `scripts/generate-benchmark.py`

```bash
python scripts/generate-benchmark.py [--output-dir data/promptsets]
```

**Output:**
```
data/promptsets/
├── benchmark-quant/
│   ├── promptset.jsonl     (250 prompts)
│   └── manifest.json
├── benchmark-finetune/
│   ├── promptset.jsonl     (250 prompts)
│   └── manifest.json
└── benchmark-eval/
    ├── promptset.jsonl     (200 prompts)
    └── manifest.json
```

### Prompt Generation Strategy

| Strategy | Used For | How |
|----------|----------|-----|
| Programmatic | math, regression math | Seeded RNG generates arithmetic with computed answers |
| Template pairs | regression (capitals, science) | (question, answer) pairs expanded to prompt dicts |
| Handcrafted | reasoning, code, factual, domain, eval | Individually written tuples |

All generation uses `seed=42` for reproducibility.

---

## Observability

Benchmark runs emit the same OTEL telemetry as regular harness runs:
- `lab_harness_requests_total` — counter per prompt
- `lab_harness_pass_total` / `lab_harness_fail_total` — pass/fail counters
- `lab_harness_latency_ms` — histogram per prompt

Traces include:
- `promptset.id` — benchmark-quant, benchmark-finetune, benchmark-eval
- `lab.team` — quant, finetune, eval
- `run.id` — bench-{team}-{suffix}
- `prompt.category` — math, reasoning, code, medical, legal, etc.

Dashboard queries can filter by `promptset=~"benchmark-.*"` to isolate benchmark data.

---

## Files Modified

| File | Change |
|------|--------|
| `scripts/generate-benchmark.py` | **NEW** — 859-line benchmark generator |
| `data/promptsets/benchmark-quant/` | **NEW** — 250 prompts |
| `data/promptsets/benchmark-finetune/` | **NEW** — 250 prompts |
| `data/promptsets/benchmark-eval/` | **NEW** — 200 prompts |
| `services/data-engine/api.py` | Added `BenchmarkRunRequest`, `BenchmarkRunSummary`, `POST /harness/benchmark`, `GET /harness/benchmark/{id}` |
| `grafana-plugins/.../opsApi.ts` | Added `BenchmarkRunSummary` interface, `startBenchmark()`, `getBenchmarkRun()` |
| `grafana-plugins/.../HarnessConsole.tsx` | Added "Run Benchmark" button, benchmark progress display, raised max_prompts to 5000 |
| `docs/design-12-benchmark.md` | **NEW** — This document |

---

## Implementation Checklist

### Benchmark Promptsets
- [x] Generate benchmark-quant (250 prompts, 5 categories)
- [x] Generate benchmark-finetune (250 prompts, 5 categories)
- [x] Generate benchmark-eval (200 prompts, 4 categories)
- [x] All promptsets have manifest.json with checksums

### API
- [x] BenchmarkRunRequest model
- [x] BenchmarkRunSummary model with per-team tracking
- [x] POST /harness/benchmark endpoint
- [x] GET /harness/benchmark/{id} endpoint
- [x] Sequential team execution with per-team status
- [x] Aggregated summary on completion

### UI
- [x] "Run Benchmark" button (orange, distinct from green "Run Harness")
- [x] Benchmark progress display with per-team status badges
- [x] Benchmark results summary table
- [x] Polling for benchmark status updates
- [x] Max prompts cap raised to 5000

### Observability
- [x] Benchmark runs emit standard OTEL metrics
- [x] Traces tagged with benchmark promptset IDs
- [x] Category-level breakdown in results
