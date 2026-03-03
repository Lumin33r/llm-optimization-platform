#!/usr/bin/env python3
"""Generate the improved Team Benchmark KPIs Grafana dashboard."""

import json
import textwrap

# ─────────────────────────────────────────────
# Helper builders
# ─────────────────────────────────────────────

def stat(id, title, desc, x, y, w, h, expr, legend, unit="short", thresholds=None):
    t = thresholds or [{"color": "green", "value": None}]
    return {
        "id": id, "type": "stat", "title": title, "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "datasource": "Prometheus",
        "targets": [{"expr": expr, "legendFormat": legend}],
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"steps": t}}},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background"}
    }

def gauge(id, title, desc, x, y, w, h, expr, legend, unit="short", mn=0, mx=100, thresholds=None):
    t = thresholds or [
        {"color": "green", "value": None},
        {"color": "yellow", "value": mx * 0.6},
        {"color": "red", "value": mx * 0.85}
    ]
    return {
        "id": id, "type": "gauge", "title": title, "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "datasource": "Prometheus",
        "targets": [{"expr": expr, "legendFormat": legend}],
        "fieldConfig": {"defaults": {"unit": unit, "min": mn, "max": mx,
                        "thresholds": {"steps": t}}},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}}
    }

def bargauge(id, title, desc, x, y, w, h, targets, unit="short", orient="horizontal", thresholds=None):
    t = thresholds or [{"color": "green", "value": None}]
    return {
        "id": id, "type": "bargauge", "title": title, "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "datasource": "Prometheus",
        "targets": targets,
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"steps": t}}},
        "options": {"orientation": orient, "displayMode": "gradient",
                    "reduceOptions": {"calcs": ["lastNotNull"]}}
    }

def timeseries(id, title, desc, x, y, w, h, targets, unit="short", fill=10, line=2):
    return {
        "id": id, "type": "timeseries", "title": title, "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "datasource": "Prometheus",
        "targets": targets,
        "fieldConfig": {"defaults": {"unit": unit,
                        "custom": {"fillOpacity": fill, "lineWidth": line}}}
    }

def row(id, title, y):
    return {
        "id": id, "type": "row", "title": title,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
        "collapsed": False, "panels": []
    }

def tgt(expr, legend, instant=False):
    t = {"expr": expr, "legendFormat": legend}
    if instant:
        t["instant"] = True
    return t

# ─────────────────────────────────────────────
# Reusable expressions
# ─────────────────────────────────────────────

def p95_latency(app):
    return f'histogram_quantile(0.95, sum by (le)(rate(vllm:e2e_request_latency_seconds_bucket{{app="{app}",job="vllm-models"}}[15m])))'

def throughput(app):
    return f'vllm:avg_generation_throughput_toks_per_s{{app="{app}",job="vllm-models"}}'

def ttft(app):
    return f'histogram_quantile(0.95, sum by (le)(rate(vllm:time_to_first_token_seconds_bucket{{app="{app}",job="vllm-models"}}[15m])))'

def gpu_cache(app):
    return f'vllm:gpu_cache_usage_perc{{app="{app}",job="vllm-models"}} * 100'

def req_running(app):
    return f'vllm:num_requests_running{{app="{app}",job="vllm-models"}}'

def req_waiting(app):
    return f'vllm:num_requests_waiting{{app="{app}",job="vllm-models"}}'

def req_rate(app):
    return f'sum by (app)(rate(vllm:request_success_total{{app="{app}",job="vllm-models"}}[15m]))'

def harness_pass_rate(team):
    return f'sum(increase(lab_harness_pass_total{{team="{team}"}}[1h])) / sum(increase(lab_harness_requests_total{{team="{team}"}}[1h])) * 100'

def harness_latency_avg(team):
    return f'sum(rate(lab_harness_latency_ms_sum{{team="{team}"}}[15m])) / sum(rate(lab_harness_latency_ms_count{{team="{team}"}}[15m]))'

# ─────────────────────────────────────────────
# Thresholds
# ─────────────────────────────────────────────

latency_thresh = [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 2},
    {"color": "red", "value": 5}
]

latency_thresh_lower = [
    {"color": "green", "value": None},
    {"color": "#EAB839", "value": 1},
    {"color": "red", "value": 3}
]

cache_thresh = [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 60},
    {"color": "red", "value": 85}
]

queue_thresh = [
    {"color": "green", "value": None},
    {"color": "yellow", "value": 5},
    {"color": "red", "value": 15}
]

pass_rate_thresh = [
    {"color": "red", "value": None},
    {"color": "yellow", "value": 50},
    {"color": "green", "value": 80}
]

throughput_thresh = [
    {"color": "red", "value": None},
    {"color": "yellow", "value": 10},
    {"color": "green", "value": 30}
]

# ─────────────────────────────────────────────
# Panel definitions
# ─────────────────────────────────────────────

panels = []

# ═══════════════════════════════════════════════
# ROW 0: Overview Stats  (y=0, h=4)
# ═══════════════════════════════════════════════

panels.append(stat(
    1, "Active Models",
    "How many of the 4 vLLM models are alive. Green=4, Yellow=3, Red<3.",
    0, 0, 4, 4,
    'count(up{job="vllm-models"} == 1)',
    "Models",
    thresholds=[
        {"color": "red", "value": None},
        {"color": "yellow", "value": 3},
        {"color": "green", "value": 4}
    ]
))

panels.append(stat(
    2, "Total RPS",
    "Combined request rate across all 4 vLLM models.",
    4, 0, 4, 4,
    'sum(rate(vllm:request_success_total{job="vllm-models"}[15m]))',
    "req/s", unit="reqps"
))

panels.append(gauge(
    3, "P95 Latency (Worst)",
    "Worst P95 end-to-end latency across all models. Under 2s = green.",
    8, 0, 4, 4,
    'max(histogram_quantile(0.95, sum by (le, app)(rate(vllm:e2e_request_latency_seconds_bucket{job="vllm-models"}[15m]))))',
    "Worst P95", unit="s", mn=0, mx=10,
    thresholds=latency_thresh
))

panels.append(gauge(
    4, "Queue Depth",
    "Total requests waiting across all models. 0 = ideal. Rising = models overloaded.",
    12, 0, 4, 4,
    'sum(vllm:num_requests_waiting{job="vllm-models"})',
    "Waiting", mn=0, mx=30,
    thresholds=queue_thresh
))

panels.append(stat(
    5, "Total Throughput",
    "Combined generation throughput across all models (tokens/sec).",
    16, 0, 4, 4,
    'sum(vllm:avg_generation_throughput_toks_per_s{job="vllm-models"})',
    "tok/s", unit="short",
    thresholds=throughput_thresh
))

panels.append(gauge(
    6, "GPU Cache Avg",
    "Average GPU KV-cache usage across all models. Under 60% = green.",
    20, 0, 4, 4,
    'avg(vllm:gpu_cache_usage_perc{job="vllm-models"}) * 100',
    "Cache %", unit="percent", mn=0, mx=100,
    thresholds=cache_thresh
))

# ═══════════════════════════════════════════════
# ROW 1: Quant Team — AWQ vs FP16  (y=4)
# ═══════════════════════════════════════════════

panels.append(row(10, "⚡ Quant Team — AWQ vs FP16", 4))

# Top sub-row (y=5): bargauge comparisons
panels.append(bargauge(
    11, "P95 Latency — AWQ vs FP16",
    "End-to-end P95 latency comparison. AWQ should be significantly lower than FP16 baseline.",
    0, 5, 8, 7,
    [tgt(p95_latency("mistral-7b-awq"), "AWQ (4-bit)"),
     tgt(p95_latency("mistral-7b-fp16"), "FP16 Baseline")],
    unit="s", thresholds=latency_thresh
))

panels.append(bargauge(
    12, "Throughput — AWQ vs FP16",
    "Generation throughput (tokens/sec). AWQ should generate tokens faster due to smaller model.",
    8, 5, 8, 7,
    [tgt(throughput("mistral-7b-awq"), "AWQ (4-bit)"),
     tgt(throughput("mistral-7b-fp16"), "FP16 Baseline")],
    unit="short", thresholds=throughput_thresh
))

panels.append(bargauge(
    13, "TTFT — AWQ vs FP16",
    "Time to first token. AWQ should prefill faster. Lower is better.",
    16, 5, 8, 7,
    [tgt(ttft("mistral-7b-awq"), "AWQ (4-bit)"),
     tgt(ttft("mistral-7b-fp16"), "FP16 Baseline")],
    unit="s", thresholds=latency_thresh_lower
))

# Bottom sub-row (y=12): gauge + harness metrics
panels.append(gauge(
    14, "GPU Cache — AWQ",
    "AWQ model KV-cache usage. Should be lower than FP16 due to 4-bit quantization.",
    0, 12, 6, 7,
    gpu_cache("mistral-7b-awq"), "AWQ Cache",
    unit="percent", mn=0, mx=100, thresholds=cache_thresh
))

panels.append(gauge(
    15, "GPU Cache — FP16",
    "FP16 baseline KV-cache usage. Higher memory footprint expected.",
    6, 12, 6, 7,
    gpu_cache("mistral-7b-fp16"), "FP16 Cache",
    unit="percent", mn=0, mx=100, thresholds=cache_thresh
))

panels.append(stat(
    16, "Quant Pass Rate",
    "Benchmark validation pass rate for the Quant team. Proves AWQ maintains quality despite compression.",
    12, 12, 6, 7,
    harness_pass_rate("quant"), "Pass %",
    unit="percent", thresholds=pass_rate_thresh
))

panels.append(bargauge(
    17, "Quant Harness Latency",
    "Average end-to-end harness latency including gateway routing, by team.",
    18, 12, 6, 7,
    [tgt(harness_latency_avg("quant"), "Quant Latency")],
    unit="ms", thresholds=[
        {"color": "green", "value": None},
        {"color": "yellow", "value": 500},
        {"color": "red", "value": 2000}
    ]
))

# ═══════════════════════════════════════════════
# ROW 2: Finetune Team — LoRA vs FP16  (y=19)
# ═══════════════════════════════════════════════

panels.append(row(20, "🧬 Finetune Team — LoRA vs FP16", 19))

panels.append(bargauge(
    21, "P95 Latency — LoRA vs FP16",
    "End-to-end P95 latency. LoRA should be close to FP16 (adapter adds minimal overhead).",
    0, 20, 8, 7,
    [tgt(p95_latency("mistral-7b-lora"), "LoRA"),
     tgt(p95_latency("mistral-7b-fp16"), "FP16 Baseline")],
    unit="s", thresholds=latency_thresh
))

panels.append(bargauge(
    22, "Throughput — LoRA vs FP16",
    "Generation throughput. LoRA should match or slightly trail FP16.",
    8, 20, 8, 7,
    [tgt(throughput("mistral-7b-lora"), "LoRA"),
     tgt(throughput("mistral-7b-fp16"), "FP16 Baseline")],
    unit="short", thresholds=throughput_thresh
))

panels.append(bargauge(
    23, "TTFT — LoRA vs FP16",
    "Time to first token. LoRA adapter should add minimal prefill overhead.",
    16, 20, 8, 7,
    [tgt(ttft("mistral-7b-lora"), "LoRA"),
     tgt(ttft("mistral-7b-fp16"), "FP16 Baseline")],
    unit="s", thresholds=latency_thresh_lower
))

panels.append(gauge(
    24, "GPU Cache — LoRA",
    "LoRA model KV-cache usage. Should be similar to FP16 (adapter barely affects memory).",
    0, 27, 6, 7,
    gpu_cache("mistral-7b-lora"), "LoRA Cache",
    unit="percent", mn=0, mx=100, thresholds=cache_thresh
))

panels.append(gauge(
    25, "GPU Cache — FP16",
    "FP16 baseline KV-cache usage for comparison with LoRA.",
    6, 27, 6, 7,
    gpu_cache("mistral-7b-fp16"), "FP16 Cache",
    unit="percent", mn=0, mx=100, thresholds=cache_thresh
))

panels.append(stat(
    26, "Finetune Pass Rate",
    "Benchmark validation pass rate for the Finetune team. Shows if LoRA specialization improves quality.",
    12, 27, 6, 7,
    harness_pass_rate("finetune"), "Pass %",
    unit="percent", thresholds=pass_rate_thresh
))

panels.append(bargauge(
    27, "Finetune Harness Latency",
    "Average end-to-end harness latency for finetune team benchmarks.",
    18, 27, 6, 7,
    [tgt(harness_latency_avg("finetune"), "Finetune Latency")],
    unit="ms", thresholds=[
        {"color": "green", "value": None},
        {"color": "yellow", "value": 500},
        {"color": "red", "value": 2000}
    ]
))

# ═══════════════════════════════════════════════
# ROW 3: Eval Team — Judge Model  (y=34)
# ═══════════════════════════════════════════════

panels.append(row(30, "🔬 Eval Team — Judge Model", 34))

# Gauge row for single-model metrics
panels.append(gauge(
    31, "Judge P95 Latency",
    "Judge model P95 end-to-end latency. Used for scoring eval benchmarks.",
    0, 35, 6, 7,
    p95_latency("mistral-7b-judge"), "P95",
    unit="s", mn=0, mx=10, thresholds=latency_thresh
))

panels.append(gauge(
    32, "Judge Throughput",
    "Judge model generation throughput (tok/s).",
    6, 35, 6, 7,
    throughput("mistral-7b-judge"), "tok/s",
    unit="short", mn=0, mx=100,
    thresholds=[
        {"color": "red", "value": None},
        {"color": "yellow", "value": 10},
        {"color": "green", "value": 25}
    ]
))

panels.append(gauge(
    33, "Judge TTFT",
    "Judge model time to first token. Critical for real-time scoring.",
    12, 35, 6, 7,
    ttft("mistral-7b-judge"), "TTFT",
    unit="s", mn=0, mx=5,
    thresholds=latency_thresh_lower
))

panels.append(gauge(
    34, "Judge GPU Cache",
    "Judge model GPU KV-cache usage. Higher usage during evaluation runs.",
    18, 35, 6, 7,
    gpu_cache("mistral-7b-judge"), "Cache",
    unit="percent", mn=0, mx=100, thresholds=cache_thresh
))

# Second sub-row: queue depth trend + harness metrics
panels.append(timeseries(
    35, "Judge Queue Depth",
    "Requests running vs waiting for judge model. Rising 'waiting' = judge can't keep up with scoring.",
    0, 42, 8, 7,
    [tgt(req_running("mistral-7b-judge"), "Running"),
     tgt(req_waiting("mistral-7b-judge"), "Waiting")],
    fill=15
))

panels.append(stat(
    36, "Eval Pass Rate",
    "Benchmark validation pass rate for the Eval team.",
    8, 42, 8, 7,
    harness_pass_rate("eval"), "Pass %",
    unit="percent", thresholds=pass_rate_thresh
))

panels.append(bargauge(
    37, "Judge Tokens/Request",
    "Average tokens generated per judge request. Scoring responses should be short (50-100 tokens).",
    16, 42, 8, 7,
    [tgt(
        'rate(vllm:generation_tokens_total{app="mistral-7b-judge",job="vllm-models"}[15m]) / rate(vllm:request_success_total{app="mistral-7b-judge",job="vllm-models"}[15m])',
        "Avg tok/req"
    )],
    unit="short", thresholds=[
        {"color": "green", "value": None},
        {"color": "yellow", "value": 100},
        {"color": "red", "value": 200}
    ]
))

# ═══════════════════════════════════════════════
# ROW 4: Head-to-Head — All Models  (y=49)
# ═══════════════════════════════════════════════

panels.append(row(40, "🏆 Head-to-Head — All Models", 49))

all_models = [
    ("mistral-7b-awq", "AWQ (4-bit)"),
    ("mistral-7b-fp16", "FP16 Baseline"),
    ("mistral-7b-lora", "LoRA"),
    ("mistral-7b-judge", "Judge"),
]

panels.append(bargauge(
    41, "P95 Latency — All Models",
    "Side-by-side P95 latency. Lower is better. AWQ should win. Judge may vary with scoring load.",
    0, 50, 8, 8,
    [tgt(p95_latency(m), l) for m, l in all_models],
    unit="s", thresholds=latency_thresh
))

panels.append(bargauge(
    42, "Throughput — All Models",
    "Generation throughput comparison. Higher is better. AWQ should lead.",
    8, 50, 8, 8,
    [tgt(throughput(m), l) for m, l in all_models],
    unit="short", thresholds=throughput_thresh
))

panels.append(bargauge(
    43, "GPU Cache — All Models",
    "KV-cache usage comparison. AWQ should be lowest due to quantization.",
    16, 50, 8, 8,
    [tgt(gpu_cache(m), l) for m, l in all_models],
    unit="percent", thresholds=cache_thresh
))

panels.append(bargauge(
    44, "TTFT — All Models",
    "Time to first token comparison. Lower is better. Shows prefill speed differences.",
    0, 58, 8, 8,
    [tgt(ttft(m), l) for m, l in all_models],
    unit="s", thresholds=latency_thresh_lower
))

panels.append(bargauge(
    45, "Request Rate — All Models",
    "Per-model request rate. Shows traffic distribution during benchmark runs.",
    8, 58, 8, 8,
    [tgt(req_rate(m), l) for m, l in all_models],
    unit="reqps"
))

panels.append(timeseries(
    46, "Queue Depth — All Models",
    "Running + waiting requests per model over time. Rising 'waiting' on any model needs attention.",
    16, 58, 8, 8,
    [tgt(req_running(m), f"{l} running") for m, l in all_models] +
    [tgt('vllm:num_requests_waiting{app=~"mistral-7b-.*",job="vllm-models"}', "{{app}} waiting")],
    fill=5
))

# ═══════════════════════════════════════════════
# ROW 5: Benchmark Run Summary  (y=66) — NEW
# ═══════════════════════════════════════════════

panels.append(row(60, "📊 Benchmark Run Summary", 66))

panels.append(stat(
    61, "Total Benchmark Requests",
    "Total harness requests across all teams in the last hour.",
    0, 67, 4, 6,
    'sum(increase(lab_harness_requests_total[1h]))',
    "Requests", unit="short"
))

panels.append(gauge(
    62, "Overall Pass Rate",
    "Combined benchmark pass rate across all teams. Target: >80%.",
    4, 67, 4, 6,
    'sum(increase(lab_harness_pass_total[1h])) / sum(increase(lab_harness_requests_total[1h])) * 100',
    "Pass %", unit="percent", mn=0, mx=100,
    thresholds=pass_rate_thresh
))

panels.append(stat(
    63, "Avg Harness Latency",
    "Average end-to-end latency across all harness requests.",
    8, 67, 4, 6,
    'sum(rate(lab_harness_latency_ms_sum[15m])) / sum(rate(lab_harness_latency_ms_count[15m]))',
    "Avg Latency", unit="ms",
    thresholds=[
        {"color": "green", "value": None},
        {"color": "yellow", "value": 500},
        {"color": "red", "value": 2000}
    ]
))

panels.append(bargauge(
    64, "Pass Rate by Team",
    "Benchmark pass rate broken down by team. Shows which team's model optimization is winning.",
    12, 67, 6, 6,
    [tgt(harness_pass_rate("quant"), "Quant"),
     tgt(harness_pass_rate("finetune"), "Finetune"),
     tgt(harness_pass_rate("eval"), "Eval")],
    unit="percent", thresholds=pass_rate_thresh
))

panels.append(bargauge(
    65, "Gateway Traffic by Team",
    "Gateway request volume per team in the last hour. Confirms benchmark traffic distribution.",
    18, 67, 6, 6,
    [tgt('sum(increase(lab_gateway_requests_total{team="quant"}[1h]))', "Quant"),
     tgt('sum(increase(lab_gateway_requests_total{team="finetune"}[1h]))', "Finetune"),
     tgt('sum(increase(lab_gateway_requests_total{team="eval"}[1h]))', "Eval")],
    unit="short"
))

# ═══════════════════════════════════════════════
# ROW 6: Benchmark Traces & Logs  (y=73)
# ═══════════════════════════════════════════════

panels.append(row(50, "📝 Benchmark Traces & Logs", 73))

panels.append({
    "id": 51, "type": "logs",
    "title": "Benchmark & Harness Logs",
    "description": "Gateway and harness log entries related to benchmark runs. Filter by team, run_id, or error.",
    "gridPos": {"h": 10, "w": 12, "x": 0, "y": 74},
    "datasource": "Loki",
    "targets": [{"expr": '{namespace="platform"} |~ "bench|benchmark|harness|predict"', "legendFormat": ""}],
    "options": {"showTime": True, "sortOrder": "Descending", "enableLogDetails": True}
})

panels.append({
    "id": 52, "type": "table",
    "title": "Request Volume by Team (1h)",
    "description": "Total gateway requests per team in the last hour. Confirms benchmark traffic reached each team's model.",
    "gridPos": {"h": 10, "w": 12, "x": 12, "y": 74},
    "datasource": "Prometheus",
    "targets": [{
        "expr": 'sum by (team)(increase(lab_gateway_requests_total[1h]))',
        "legendFormat": "", "format": "table", "instant": True
    }],
    "transformations": [{
        "id": "organize",
        "options": {
            "excludeByName": {"Time": True},
            "renameByName": {"team": "Team", "Value": "Requests (1h)"}
        }
    }],
    "fieldConfig": {"defaults": {"unit": "short"}}
})

# ─────────────────────────────────────────────
# Assemble dashboard JSON
# ─────────────────────────────────────────────

dashboard = {
    "annotations": {"list": []},
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 1,
    "id": None,
    "links": [],
    "panels": panels,
    "refresh": "15s",
    "schemaVersion": 39,
    "tags": ["llm", "benchmark", "teams", "quantization", "finetuning", "evaluation", "kpi"],
    "templating": {"list": []},
    "time": {"from": "now-1h", "to": "now"},
    "title": "Team Benchmark KPIs",
    "uid": "llm-platform-overview"
}

operations_dashboard = {
    "annotations": {"list": []},
    "editable": True,
    "fiscalYearStartMonth": 0,
    "graphTooltip": 0,
    "id": None,
    "links": [],
    "panels": [{
        "id": 1,
        "title": "LLM Platform Operations",
        "type": "llmplatform-ops-panel",
        "gridPos": {"h": 24, "w": 24, "x": 0, "y": 0},
        "options": {"gatewayUrl": "/gateway-proxy"}
    }],
    "refresh": "30s",
    "schemaVersion": 39,
    "tags": ["llm", "operations"],
    "templating": {"list": []},
    "time": {"from": "now-1h", "to": "now"},
    "title": "LLM Operations Console",
    "uid": "llm-operations-console"
}

# ─────────────────────────────────────────────
# Build YAML ConfigMap
# ─────────────────────────────────────────────

platform_json = json.dumps(dashboard, indent=2)
ops_json = json.dumps(operations_dashboard, indent=2)

# Indent JSON for YAML literal block (4 spaces)
platform_indented = "\n".join("    " + line if line else "" for line in platform_json.splitlines())
ops_indented = "\n".join("    " + line if line else "" for line in ops_json.splitlines())

yaml_output = f"""# k8s/base/observability/grafana-dashboards.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards-provider
  namespace: observability
data:
  dashboards.yaml: |
    apiVersion: 1
    providers:
      - name: 'llm'
        orgId: 1
        folder: 'LLM Platform'
        type: file
        disableDeletion: false
        editable: true
        options:
          path: /var/lib/grafana/dashboards/llm
      - name: 'kubernetes'
        orgId: 1
        folder: 'Kubernetes'
        type: file
        disableDeletion: false
        editable: true
        options:
          path: /var/lib/grafana/dashboards/k8s
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards
  namespace: observability
data:
  llm-platform.json: |
{platform_indented}

  llm-operations.json: |
{ops_indented}
"""

# Write the file
output_path = "/home/lumineer/codeplatoon/projects/llm-optimization-platform/k8s/base/observability/grafana-dashboards.yaml"
with open(output_path, "w") as f:
    f.write(yaml_output)

print(f"Dashboard written to {output_path}")
print(f"Total panels: {len(panels)}")
print(f"Panel types: {dict(sorted({p.get('type','?'): sum(1 for q in panels if q.get('type')==p.get('type')) for p in panels}.items()))}")
