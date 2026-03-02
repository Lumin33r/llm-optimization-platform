# Design Document 11: Team Benchmark KPI Dashboard

## Purpose

Replace the generic "LLM Platform Overview" dashboard with a **comparative benchmark results dashboard** that shows each team's model performance against the FP16 baseline. After running a benchmark (700 prompts via Design-12) or individual harness/test runs, this dashboard makes it immediately clear how each optimized model compares to the reference.

**Key Questions This Dashboard Answers:**

| Team | Question | Panel(s) |
|------|----------|----------|
| Quantization | "Is AWQ faster than FP16 while maintaining quality?" | P95 Latency, Throughput, GPU Cache |
| Quantization | "Does 4-bit quantization reduce memory?" | GPU KV-Cache comparison |
| Fine-Tuning | "Does the LoRA adapter add latency overhead?" | P95 Latency, TTFT comparison |
| Fine-Tuning | "Is domain-adapted throughput comparable?" | Throughput, Decode Time |
| Evaluation | "Can the judge model keep up with scoring demand?" | Queue Depth, Active Requests |
| Evaluation | "How fast does it score?" | P95 Latency, Throughput |
| Lab Lead | "Which model is the overall winner?" | Head-to-Head row |
| Lab Lead | "What happened during the last benchmark?" | Traces & Logs row |

**Depends On:** [design-09-data-engine.md](design-09-data-engine.md), [design-10-models.md](design-10-models.md), [design-12-benchmark.md](design-12-benchmark.md)

---

## Model Inventory

| Team | Model Variant | Pod | Prometheus `app` Label | Role |
|------|--------------|-----|----------------------|------|
| Quantization | AWQ 4-bit | `mistral-7b-awq` | `mistral-7b-awq` | Compressed inference |
| Fine-Tuning | LoRA adapter | `mistral-7b-lora` | `mistral-7b-lora` | Domain-adapted |
| Evaluation | Judge | `mistral-7b-judge` | `mistral-7b-judge` | Response scoring |
| _Baseline_ | FP16 full-precision | `mistral-7b-fp16` | `mistral-7b-fp16` | Reference for comparison |

All models run on SPOT `g4dn.xlarge` GPU instances in the `llm-baseline` namespace. The baseline (FP16) is the control — every team's model is measured against it.

---

## Dashboard Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Dashboard: "Team Benchmark KPIs"                                    │
│  UID: llm-platform-overview   Folder: LLM Platform                   │
│  Datasources: Prometheus (metrics), Loki (logs)                      │
│                                                                      │
│  ┌─── Row 1: Overview Strip ────────────────────────────────────────┐│
│  │ Active │ Total │ P95 Avg │ Waiting │ Throughput │ GPU     ││
│  │ Models │  RPS  │ Latency │ Queue   │  Avg tok/s │ Cache % ││
│  └──────────────────────────────────────────────────────────────────┘│
│  ┌─── Row 2: Quantization — AWQ vs FP16 Baseline ──────────────────┐│
│  │ P95 Latency       │ Throughput (tok/s) │ Time to First Token    ││
│  │ ── AWQ  ── FP16   │ ── AWQ  ── FP16    │ ── AWQ  ── FP16       ││
│  ├────────────────────┼────────────────────┼────────────────────────┤│
│  │ GPU KV-Cache %     │ Decode Time/Token  │ Tokens Generated       ││
│  │ ── AWQ  ── FP16   │ ── AWQ  ── FP16    │ ── AWQ  ── FP16       ││
│  └──────────────────────────────────────────────────────────────────┘│
│  ┌─── Row 3: Fine-Tuning — LoRA vs FP16 Baseline ──────────────────┐│
│  │ P95 Latency       │ Throughput (tok/s) │ Time to First Token    ││
│  │ ── LoRA  ── FP16  │ ── LoRA  ── FP16   │ ── LoRA  ── FP16      ││
│  ├────────────────────┼────────────────────┼────────────────────────┤│
│  │ GPU KV-Cache %     │ Decode Time/Token  │ Tokens Generated       ││
│  │ ── LoRA  ── FP16  │ ── LoRA  ── FP16   │ ── LoRA  ── FP16      ││
│  └──────────────────────────────────────────────────────────────────┘│
│  ┌─── Row 4: Evaluation — Judge Model ──────────────────────────────┐│
│  │ P95 Latency       │ Throughput (tok/s) │ Time to First Token    ││
│  │ ── Judge          │ ── Judge           │ ── Judge               ││
│  ├────────────────────┼────────────────────┼────────────────────────┤│
│  │ GPU KV-Cache %     │ Queue Depth        │ Tokens per Request     ││
│  │ ── Judge          │ running / waiting  │ ── Judge               ││
│  └──────────────────────────────────────────────────────────────────┘│
│  ┌─── Row 5: Head-to-Head — All Models ─────────────────────────────┐│
│  │ P95 Latency (4 lines) │ Throughput (4 lines) │ GPU Cache (4)    ││
│  │ Request Rate (4 lines)│ TTFT (4 lines)       │ Queue (4)        ││
│  └──────────────────────────────────────────────────────────────────┘│
│  ┌─── Row 6: Benchmark Traces & Logs ──────────────────────────────┐│
│  │ Gateway Request Log (Loki)     │ Request Volume by Team (table) ││
│  └──────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Row-by-Row Specification

### Row 1: Overview Strip

Quick-scan stat panels. A lab lead should absorb cluster status in under 5 seconds.

| Panel | Type | Width | PromQL | Thresholds | Interpretation |
|-------|------|-------|--------|------------|----------------|
| Active Models | stat | 4 | `count(up{app=~"mistral-7b-.*"} == 1)` | 4=green, 3=yellow, <3=red | All 4 models alive? |
| Total RPS | stat | 4 | `sum(rate(vllm:request_success_total{app=~"mistral-7b-.*"}[5m]))` | — | Platform-wide request rate |
| P95 Latency Avg | stat | 4 | `avg(histogram_quantile(0.95, sum by (le,app)(rate(vllm:e2e_request_latency_seconds_bucket{app=~"mistral-7b-.*"}[5m]))))` | <2s green, <5s yellow, >5s red | Overall latency health |
| Waiting Queue | stat | 4 | `sum(vllm:num_requests_waiting{app=~"mistral-7b-.*"})` | 0=green, >0=yellow, >10=red | Any backpressure? |
| Avg Throughput | stat | 4 | `avg(vllm:avg_generation_throughput_toks_per_s{app=~"mistral-7b-.*"})` | — | Tokens/sec across models |
| GPU Cache Avg | stat | 4 | `avg(vllm:gpu_cache_usage_perc{app=~"mistral-7b-.*"}) * 100` | <70=green, <90=yellow, >90=red | Memory pressure? |

---

### Row 2: Quantization Team — AWQ vs FP16 Baseline

**What the Quantization team cares about:** AWQ (4-bit) should be **faster** than FP16 (less compute per weight) and use **less GPU memory** (4-bit vs 16-bit). The tradeoff is potential quality degradation on precision-sensitive tasks (math, code). Benchmark categories `math`, `reasoning`, `code`, `factual`, and `long_form` stress-test this tradeoff.

| Panel | Type | Queries | What to Look For |
|-------|------|---------|------------------|
| P95 E2E Latency | timeseries | AWQ P95, FP16 P95 | AWQ line should be **below** FP16 — faster inference |
| Generation Throughput | timeseries | AWQ tok/s, FP16 tok/s | AWQ line should be **above** FP16 — more tokens per second |
| Time to First Token | timeseries | AWQ TTFT P95, FP16 TTFT P95 | AWQ should have **lower** TTFT — faster prefill |
| GPU KV-Cache Usage | timeseries | AWQ %, FP16 % | AWQ should be **well below** FP16 — 4-bit uses ~4× less cache |
| Decode Time per Token | timeseries | AWQ P95, FP16 P95 | AWQ should be **lower** — faster per-token generation |
| Tokens Generated | timeseries | AWQ total, FP16 total | Shows volume processed; useful for throughput regression detection |

**Key PromQL — Quantization Panels:**

```promql
# P95 E2E Latency — AWQ vs FP16
histogram_quantile(0.95, sum by (le)(rate(
  vllm:e2e_request_latency_seconds_bucket{app="mistral-7b-awq"}[5m])))
histogram_quantile(0.95, sum by (le)(rate(
  vllm:e2e_request_latency_seconds_bucket{app="mistral-7b-fp16"}[5m])))

# Generation Throughput
vllm:avg_generation_throughput_toks_per_s{app="mistral-7b-awq"}
vllm:avg_generation_throughput_toks_per_s{app="mistral-7b-fp16"}

# TTFT P95
histogram_quantile(0.95, sum by (le)(rate(
  vllm:time_to_first_token_seconds_bucket{app="mistral-7b-awq"}[5m])))
histogram_quantile(0.95, sum by (le)(rate(
  vllm:time_to_first_token_seconds_bucket{app="mistral-7b-fp16"}[5m])))

# GPU KV-Cache
vllm:gpu_cache_usage_perc{app="mistral-7b-awq"} * 100
vllm:gpu_cache_usage_perc{app="mistral-7b-fp16"} * 100

# Decode Time per Token P95
histogram_quantile(0.95, sum by (le)(rate(
  vllm:time_per_output_token_seconds_bucket{app="mistral-7b-awq"}[5m])))
histogram_quantile(0.95, sum by (le)(rate(
  vllm:time_per_output_token_seconds_bucket{app="mistral-7b-fp16"}[5m])))

# Tokens Generated (cumulative)
vllm:generation_tokens_total{app="mistral-7b-awq"}
vllm:generation_tokens_total{app="mistral-7b-fp16"}
```

**Reading the Results After a Benchmark Run:**

After running the 250-prompt `benchmark-quant` battery, look for:
- **Latency gap**: AWQ line should sit 20-40% below FP16. If they overlap, quantization isn't providing a speed benefit on this hardware.
- **Throughput uplift**: AWQ tok/s should be 1.5-2× higher than FP16. If not, the GPU may be bottlenecked on something other than compute (e.g., memory bandwidth).
- **GPU cache delta**: AWQ should use roughly 25% of FP16's cache. If they're close, the AWQ model may not be properly quantized.
- **Quality signal**: Check the Operations Console (Design-06 plugin) for pass rate comparison. If AWQ pass rate drops vs FP16 in `math` or `code` categories, precision loss is significant.

---

### Row 3: Fine-Tuning Team — LoRA vs FP16 Baseline

**What the Fine-Tuning team cares about:** The LoRA adapter should maintain comparable **latency** and **throughput** to the base FP16 model while improving **domain quality** (medical, legal, technical). LoRA adds a small rank-decomposition matrix on top of FP16 weights, so the overhead should be minimal. Benchmark categories `medical`, `legal`, `technical`, `regression`, and `cross_domain` test domain adaptation and catastrophic forgetting.

| Panel | Type | Queries | What to Look For |
|-------|------|---------|------------------|
| P95 E2E Latency | timeseries | LoRA P95, FP16 P95 | Lines should **overlap** — LoRA shouldn't add significant latency |
| Generation Throughput | timeseries | LoRA tok/s, FP16 tok/s | Lines should be **close** — LoRA overhead should be <10% |
| Time to First Token | timeseries | LoRA TTFT P95, FP16 TTFT P95 | LoRA may be slightly higher (adapter merge) but should be close |
| GPU KV-Cache Usage | timeseries | LoRA %, FP16 % | LoRA uses the same base weights + small adapter — should be **similar** |
| Decode Time per Token | timeseries | LoRA P95, FP16 P95 | Should be nearly identical — LoRA doesn't change decode mechanics |
| Tokens Generated | timeseries | LoRA total, FP16 total | Volume comparison — useful for A/B consistency checks |

**Key PromQL — Fine-Tuning Panels:**

```promql
# P95 Latency — LoRA vs FP16
histogram_quantile(0.95, sum by (le)(rate(
  vllm:e2e_request_latency_seconds_bucket{app="mistral-7b-lora"}[5m])))
histogram_quantile(0.95, sum by (le)(rate(
  vllm:e2e_request_latency_seconds_bucket{app="mistral-7b-fp16"}[5m])))

# Throughput
vllm:avg_generation_throughput_toks_per_s{app="mistral-7b-lora"}
vllm:avg_generation_throughput_toks_per_s{app="mistral-7b-fp16"}

# TTFT
histogram_quantile(0.95, sum by (le)(rate(
  vllm:time_to_first_token_seconds_bucket{app="mistral-7b-lora"}[5m])))
histogram_quantile(0.95, sum by (le)(rate(
  vllm:time_to_first_token_seconds_bucket{app="mistral-7b-fp16"}[5m])))

# GPU Cache
vllm:gpu_cache_usage_perc{app="mistral-7b-lora"} * 100
vllm:gpu_cache_usage_perc{app="mistral-7b-fp16"} * 100
```

**Reading the Results After a Benchmark Run:**

After running the 250-prompt `benchmark-finetune` battery:
- **Latency parity**: LoRA and FP16 should be within 5-10% of each other. A gap >20% suggests the LoRA adapter merge is expensive.
- **Throughput parity**: Should be nearly identical. If LoRA throughput drops >15%, investigate adapter rank (lower rank = less overhead).
- **Domain quality**: Check the Operations Console for per-category pass rates. LoRA should **outperform** FP16 on `medical`, `legal`, `technical` categories (that's the whole point of fine-tuning). If LoRA passes fewer `regression` prompts than FP16, the model has catastrophic forgetting.
- **GPU cache**: If LoRA uses significantly more cache than FP16, the adapter weights are too large.

---

### Row 4: Evaluation Team — Judge Model Performance

**What the Evaluation team cares about:** The judge model (`mistral-7b-judge`) scores prompt-response pairs for coherence, helpfulness, factuality, and edge cases. Speed matters because every other team's output needs scoring. The judge doesn't compare against FP16 — it IS a standalone scoring service.

| Panel | Type | Queries | What to Look For |
|-------|------|---------|------------------|
| P95 E2E Latency | timeseries | Judge P95 | Should stay **under 3s** for interactive scoring |
| Generation Throughput | timeseries | Judge tok/s | Higher = faster scoring pipeline |
| Time to First Token | timeseries | Judge TTFT P95 | Prefill time — affected by prompt length |
| GPU KV-Cache Usage | timeseries | Judge % | If near 100%, scoring requests will queue |
| Queue Depth | timeseries | Running + Waiting | Rising `waiting` line = judge can't keep up |
| Avg Tokens per Request | timeseries | Judge avg tokens/req | Scoring responses should be short (~50-100 tokens) |

**Key PromQL — Evaluation Panels:**

```promql
# P95 Latency
histogram_quantile(0.95, sum by (le)(rate(
  vllm:e2e_request_latency_seconds_bucket{app="mistral-7b-judge"}[5m])))

# Throughput
vllm:avg_generation_throughput_toks_per_s{app="mistral-7b-judge"}

# Queue Depth
vllm:num_requests_running{app="mistral-7b-judge"}
vllm:num_requests_waiting{app="mistral-7b-judge"}

# Avg tokens per request (generation)
rate(vllm:generation_tokens_total{app="mistral-7b-judge"}[5m])
  / rate(vllm:request_success_total{app="mistral-7b-judge"}[5m])
```

**Reading the Results After a Benchmark Run:**

After running the 200-prompt `benchmark-eval` battery:
- **Latency**: Should be consistent across categories. If `edge_case` prompts spike latency, the judge struggles with ambiguous inputs.
- **Queue pressure**: During benchmark, `waiting` should stay near 0 with concurrency=10. If it rises, the judge model needs more replicas or the concurrency is too high.
- **Scoring consistency**: Check the Operations Console for pass rates across `coherence`, `helpfulness`, `factuality`, `edge_case`. A well-calibrated judge should have consistent pass rates (~80-95%) except `edge_case` which may be intentionally harder.
- **Token efficiency**: Judge responses should be short (scores/explanations). If avg tokens/request is high (>200), the judge may be over-generating.

---

### Row 5: Head-to-Head — All Models

The "Monday morning lab lead" row. All 4 models on the same graph — one line per model.

| Panel | Type | Queries | What to Look For |
|-------|------|---------|------------------|
| P95 Latency — All Models | timeseries | 4 series | AWQ should be lowest, LoRA ≈ FP16, Judge varies |
| Throughput — All Models | timeseries | 4 series | AWQ should be highest, LoRA ≈ FP16 |
| GPU Cache — All Models | timeseries | 4 series | AWQ lowest, FP16 ≈ LoRA, Judge depends on load |
| Request Rate — All Models | timeseries | 4 series | Shows traffic distribution across models |
| TTFT — All Models | timeseries | 4 series | AWQ should be lowest (smaller model) |
| Queue — All Models | timeseries | 4 series (running+waiting) | Any model queuing = capacity concern |

---

### Row 6: Benchmark Traces & Logs

Correlates benchmark runs with observable traces and log entries.

| Panel | Type | Datasource | Query | Purpose |
|-------|------|-----------|-------|---------|
| Benchmark Run Logs | logs | Loki | `{namespace="platform"} \|~ "bench\|benchmark\|harness"` | See harness execution logs, errors, timing |
| Gateway Requests by Team | table | Prometheus | `sum by (team)(increase(lab_gateway_requests_total[1h]))` | Volume per team in last hour — confirms benchmark ran |

---

## Metric Sources

### vLLM Native Metrics (Prometheus)

These are emitted by each vLLM model pod and scraped by Prometheus every 15s. They reflect real-time model performance — including during benchmark runs.

| Metric | Type | Labels | Dashboard Use |
|--------|------|--------|---------------|
| `vllm:e2e_request_latency_seconds` | histogram | `app` | P95/P99 latency comparison |
| `vllm:time_to_first_token_seconds` | histogram | `app` | Prefill speed comparison |
| `vllm:time_per_output_token_seconds` | histogram | `app` | Decode efficiency comparison |
| `vllm:avg_generation_throughput_toks_per_s` | gauge | `app` | Raw throughput comparison |
| `vllm:gpu_cache_usage_perc` | gauge | `app` | Memory efficiency comparison |
| `vllm:num_requests_running` | gauge | `app` | Active load indicator |
| `vllm:num_requests_waiting` | gauge | `app` | Backpressure indicator |
| `vllm:request_success_total` | counter | `app` | Request volume |
| `vllm:generation_tokens_total` | counter | `app` | Token volume |
| `vllm:prompt_tokens_total` | counter | `app` | Input volume |
| `vllm:request_generation_tokens` | histogram | `app` | Tokens per request distribution |

### Gateway Metrics (OTEL → Prometheus)

| Metric | Type | Labels | Dashboard Use |
|--------|------|--------|---------------|
| `lab_gateway_requests_total` | counter | `team`, `status` | Request count by team |
| `lab_gateway_request_duration_ms` | histogram | `team` | Gateway-level latency |

### Harness Metrics (OTEL → Prometheus)

Emitted by the test harness during benchmark and harness runs:

| Metric | Type | Labels | Dashboard Use |
|--------|------|--------|---------------|
| `lab_harness_requests_total` | counter | `scenario_id`, `team` | Benchmark prompt count |
| `lab_harness_pass_total` | counter | `scenario_id`, `team` | Pass count |
| `lab_harness_fail_total` | counter | `scenario_id`, `team` | Fail count |
| `lab_harness_latency_ms` | histogram | `scenario_id`, `team` | Per-prompt latency |

### Harness Result Fields (API — visible in Operations Console)

The `HarnessResult` dataclass includes per-prompt comparison data:

| Field | Type | Meaning |
|-------|------|---------|
| `passed` | bool | Did team model's response pass validation? |
| `latency_ms` | float | Team model response time |
| `tokens_per_second` | float | Team model throughput |
| `category` | string | Benchmark category (math, medical, etc.) |
| `baseline_response` | string | FP16 baseline response (when `--compare-baseline`) |
| `baseline_latency_ms` | float | FP16 response time |
| `baseline_passed` | bool | Did FP16 response pass validation? |

---

## How to Use This Dashboard

### After Running a Benchmark (Design-12)

1. Click **Run Benchmark** (orange button) in the LLM Operations Console
2. Wait for all 3 teams to complete (~5-15 minutes depending on concurrency)
3. Switch to **Team Benchmark KPIs** dashboard
4. Set time range to cover the benchmark window (e.g., "Last 30 minutes")
5. **Scan Row 1** — are all 4 models active? Any queue pressure?
6. **Check your team's row** — compare your model's lines against the FP16 baseline
7. **Check Head-to-Head** — see how your model ranks against all others
8. **Review Operations Console** — pass rates and category breakdown for quality signal

### After a Harness Run (Single Team)

1. Click **Run Harness** for your team in the Operations Console
2. Set dashboard time range to cover the run
3. Your team's row will show the performance profile during that window
4. The FP16 baseline lines provide the comparison (if FP16 also received traffic)

### Daily Monitoring

The dashboard auto-refreshes every 15 seconds. Use the Overview Strip for a quick health check without scrolling.

---

## Dashboard Panels Summary

| ID | Row | Panel Title | Type | Series |
|----|-----|------------|------|--------|
| 1-6 | Overview | Active Models, RPS, P95 Avg, Queue, Throughput, GPU | stat | 1 each |
| 10 | Quant | _Row: Quantization — AWQ vs FP16 Baseline_ | row | — |
| 11-13 | Quant | P95 Latency, Throughput, TTFT | timeseries | 2 each (AWQ + FP16) |
| 14-16 | Quant | GPU Cache, Decode Time, Tokens Generated | timeseries | 2 each (AWQ + FP16) |
| 20 | Finetune | _Row: Fine-Tuning — LoRA vs FP16 Baseline_ | row | — |
| 21-23 | Finetune | P95 Latency, Throughput, TTFT | timeseries | 2 each (LoRA + FP16) |
| 24-26 | Finetune | GPU Cache, Decode Time, Tokens Generated | timeseries | 2 each (LoRA + FP16) |
| 30 | Eval | _Row: Evaluation — Judge Model_ | row | — |
| 31-33 | Eval | P95 Latency, Throughput, TTFT | timeseries | 1 each (Judge) |
| 34-36 | Eval | GPU Cache, Queue Depth, Tokens/Request | timeseries | 1-2 each |
| 40 | H2H | _Row: Head-to-Head — All Models_ | row | — |
| 41-46 | H2H | Latency, Throughput, GPU, Requests, TTFT, Queue | timeseries | 4 each |
| 50 | Logs | _Row: Benchmark Traces & Logs_ | row | — |
| 51 | Logs | Gateway Request Log | logs | Loki |
| 52 | Logs | Request Volume by Team | table | Prometheus |

**Total: 34 panels** across 6 collapsible rows.

---

## Connection to Other Dashboards

| Dashboard | Purpose | Relationship |
|-----------|---------|-------------|
| **Team Benchmark KPIs** (this) | Comparative model performance metrics | Shows WHAT happened during benchmark |
| **LLM Operations Console** | Operational actions + pass/fail results | Shows WHETHER prompts passed + lets you run benchmarks |
| **Kubernetes Cluster Overview** | Node/pod health | Shows infrastructure health during benchmark runs |
| **Kubernetes Node Overview** | Per-node CPU/memory/disk | Shows GPU node resource pressure during benchmark |

---

## Files Modified

| File | Change |
|------|--------|
| `k8s/base/observability/grafana-dashboards.yaml` | Replaced `llm-platform.json` dashboard with team-comparative KPI panels |
| `docs/design-11-team-dashboards.md` | Redesigned from generic overview to benchmark-comparative KPI specification |
