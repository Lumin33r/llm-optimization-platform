# Design Document 11: Team-Facing Grafana Dashboards

## Scenario Context

**Scenario 3 — Small AI Lab**: A platform engineering team supports three internal teams that experiment with and optimize open-source LLMs:

| Team | Mission | Model Variant | Pod |
|------|---------|--------------|-----|
| **Quantization** | Compare compressed (AWQ 4-bit) inference quality against full-precision baselines | AWQ | `mistral-7b-awq` |
| **Fine-Tuning** | Run LoRA-adapted models on domain-specific data, A/B comparison against base | LoRA | `mistral-7b-lora` |
| **Evaluation** | Score prompt-response pairs for coherence, factuality, toxicity to rank model variants | Judge | `mistral-7b-judge` |
| _Reference_ | Full-precision baseline for comparison | FP16 | `mistral-7b-fp16` |

### Monday Morning Lab Lead Questions

> - Are all three endpoints live?
> - Which model versions are deployed?
> - Is the quantization team burning extra compute from testing a 70B variant?

---

## Dashboard Layout

### Dashboard 1: "LLM Platform Overview" (Prometheus)

_Path: Grafana sidebar → Dashboards → LLM Platform Overview_

This is the **"Monday morning lab lead"** dashboard — all Prometheus-backed, real-time time series.

| Row | Panel | Type | Who Cares | What It Answers |
|-----|-------|------|-----------|-----------------|
| Top | **Team → Model Routing** | text (markdown table) | Everyone | Which team uses which model — quick reference |
| 2 | **Request Rate by Model** | timeseries | Lab lead | "Who's generating the most traffic?" — each model is a different line |
| 2 | **Total RPS** | stat | Lab lead | Single number — platform-wide request rate |
| 2 | **Total Running Requests** | stat | Lab lead | How many in-flight right now |
| 2 | **Waiting Requests (queue overflow)** | stat | Lab lead | Anything queued? Green/yellow/red thresholds |
| 2 | **Active Models** | stat | Lab lead | How many of the 4 models are alive |
| 3 | **Generation Throughput by Model (tok/s)** | timeseries | Quant + Finetune | "Is AWQ faster than FP16?" / "How does LoRA compare?" — side-by-side lines |
| 3 | **Queue Depth by Model** | timeseries | Eval team | "Is the judge model overloaded?" — rising `waiting` line = needs more capacity |
| 4 | **GPU KV-Cache Usage by Model** | timeseries | Lab lead + Quant | "Is one model burning extra GPU memory?" — AWQ should use less than FP16 |
| 4 | **GPU KV-Cache per Model** | bargauge | Lab lead | Instant snapshot — horizontal bars with green/yellow/red thresholds |

#### Key PromQL Queries

```promql
# Request rate per model
sum by (app)(rate(vllm:request_success_total{namespace="llm-baseline"}[5m]))

# Generation throughput per model
vllm:avg_generation_throughput_toks_per_s{namespace="llm-baseline"}

# Queue depth per model
vllm:num_requests_running{namespace="llm-baseline"}
vllm:num_requests_waiting{namespace="llm-baseline"}

# GPU KV-cache per model
vllm:gpu_cache_usage_perc{namespace="llm-baseline"} * 100

# Active model count
count(up{namespace="llm-baseline", app=~"mistral-7b-.*"} == 1)
```

All queries use the `app` label (relabeled from `__meta_kubernetes_pod_label_app` in the Prometheus `kubernetes-pods` scrape config) to split metrics by model variant.

---

### Dashboard 2: "LLM Operations Console" (Custom Grafana Plugin)

_Path: Grafana sidebar → Dashboards → LLM Operations Console_

This is the **"platform engineer"** dashboard — operational actions, not just metrics.

| Section | Component | Who Cares | What It Does |
|---------|-----------|-----------|-------------|
| Top-left | **HealthOverview** | Lab lead | Are all 3 team endpoints + gateway green? |
| Top-right | **StatsCards** | Lab lead | 24h totals, error rate, P50/P95/P99 latency, **requests by team** |
| Middle | **ServicesTable** | Lab lead | Which image versions are deployed? Namespace isolation visible |
| Middle | **TestConsole** | Any team | Quick "send one prompt to my model" sanity check |
| Bottom | **HarnessConsole** | All teams | Batch quality testing: pick team + promptset → run → see pass rate, tok/s, category breakdown |

#### StatsCards — Metrics Displayed

- Total Requests (24h)
- Error Rate (%)
- P50 / P95 / P99 Latency (ms)
- Requests by Team (quant / finetune / eval breakdown)

#### HarnessConsole — Team-Specific Promptsets

| Team | Promptset | Prompts | Measures |
|------|-----------|---------|----------|
| Quantization | `quant-quality` | 30 | AWQ output quality vs baseline |
| Fine-Tuning | `finetune-domain` | 30 | Domain-specific accuracy (legal, medical, code) |
| Evaluation | `eval-calibration` | 20 | Judge scoring consistency and calibration |
| _Any_ | `canary` | 50 | Quick factual correctness smoke test |
| _Any_ | `performance` | 100 | Throughput and latency under load |

---

## Team-Specific Workflows

### Quantization Team

1. **Overview** → "Generation Throughput by Model" → compare `mistral-7b-awq` line vs `mistral-7b-fp16` line
2. **Overview** → "GPU KV-Cache by Model" → verify AWQ uses less GPU memory than FP16
3. **Operations** → HarnessConsole → Team=`Quantization`, Promptset=`quant-quality` → Run → check pass rate vs baseline
4. **Operations** → HarnessConsole → compare `--compare-baseline` results: is AWQ quality within acceptable delta of FP16?

### Fine-Tuning Team

1. **Overview** → "Generation Throughput by Model" → compare `mistral-7b-lora` vs `mistral-7b-fp16`
2. **Operations** → HarnessConsole → Team=`Fine-tuning`, Promptset=`finetune-domain` → Run → verify domain-specific quality
3. **Operations** → HarnessConsole → category breakdown shows per-domain scores (legal, medical, code)

### Evaluation Team

1. **Overview** → "Queue Depth by Model" → is `mistral-7b-judge` backing up? Rising `waiting` line means scoring latency will increase
2. **Operations** → HarnessConsole → Team=`Evaluation`, Promptset=`eval-calibration` → Run → verify judge scoring consistency
3. **Operations** → TestConsole → send individual prompt-response pairs to `/score` for manual scoring checks

### Lab Lead (Monday Morning)

1. **Overview** → stat cards → all 4 models active? Anything queued?
2. **Overview** → "Request Rate by Model" → who's been busy over the weekend?
3. **Overview** → "GPU KV-Cache per Model" → any model memory-hungry?
4. **Operations** → HealthOverview → all green?
5. **Operations** → StatsCards → error rate near 0%? Latency reasonable?
6. **Operations** → ServicesTable → correct image tags deployed?

---

## Architecture Notes

### Why Two Dashboards?

| Dashboard | Data Source | Refresh | Purpose |
|-----------|-----------|---------|---------|
| **Platform Overview** | Prometheus (native Grafana datasource) | Auto (configurable) | Time-series metrics — trends, comparisons, capacity planning |
| **Operations Console** | Gateway REST API (custom plugin) | 30s poll | Operational actions — health checks, test runs, service inventory |

Prometheus panels are standard Grafana time series that any team member can edit, fork, or add alerts to. The Operations Console is a custom React plugin (`llmplatform-ops-panel`) that talks to the gateway's `/ops/*` endpoints.

### Metric Labels

All vLLM metrics are scraped via the `kubernetes-pods` Prometheus job and carry these labels:

- `app` — deployment name (e.g., `mistral-7b-awq`, `mistral-7b-lora`)
- `namespace` — always `llm-baseline`
- `pod` — individual pod name (for replica-level drill-down)

This allows `by (app)` grouping for per-model views, which is the primary axis for team-facing dashboards.
