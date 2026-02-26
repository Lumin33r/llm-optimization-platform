# Design Document 8: OpenTelemetry Attribute Schema

## Overview

This document defines the canonical OpenTelemetry attribute schema for the LLM Optimization Platform. The schema ensures:

- **Consistency** - Uniform attribute names across Gateway and team services
- **Compatibility** - Aligned with OTel resource attributes and GenAI semantic conventions
- **Safety** - No raw prompts/responses by default
- **Queryability** - Optimized for Grafana/Tempo/Loki/Mimir dashboards

This schema complements [design-03-observability.md](design-03-observability.md) by defining the semantic layer that makes telemetry actionable.

---

## Quick Start (Implementation Order)

```python
# 1. Prerequisites (after design-03 OTEL Collector deployed)
# Add shared telemetry module to each service

# 2. Import and configure in each service
from shared.telemetry import create_resource, setup_telemetry

resource = create_resource(
    service_name="quant-api",
    namespace="quant"
)
setup_telemetry(resource)

# 3. Use span attributes in route handlers
from shared.spans import set_route_attributes, set_genai_attributes

@app.post("/predict")
async def predict(request: PredictRequest):
    with tracer.start_as_current_span("predict") as span:
        set_route_attributes(span, team="quant", decision="direct")
        set_genai_attributes(span, model="gptq-7b-v3", input_tokens=100)
        # ... inference logic
```

**Depends On**: [design-03-observability.md](design-03-observability.md) (OTEL Collector)
**Feeds Into**: [design-09-data-engine.md](design-09-data-engine.md) (promptset tags)

---

## Architecture Integration

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              Telemetry Data Flow with Attributes                                 │
│                                                                                                  │
│   ┌─────────────────────┐                                                                       │
│   │      Gateway        │                                                                       │
│   │                     │                                                                       │
│   │  Resource Attrs:    │                                                                       │
│   │  - service.name     │                                                                       │
│   │  - lab.team         │                                                                       │
│   │  - k8s.namespace    │                                                                       │
│   │                     │                                                                       │
│   │  Span Attrs:        │    Propagation Headers:                                               │
│   │  - lab.route.*      │    ─────────────────────────►                                        │
│   │  - lab.ab.*         │    • traceparent (W3C)                                               │
│   │  - lab.timeout.ms   │    • baggage: lab.route.policy.id,                                   │
│   │                     │              lab.ab.bucket,                                          │
│   └──────────┬──────────┘              lab.experiment.id                                       │
│              │                                                                                  │
│              ▼                                                                                  │
│   ┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐             │
│   │     quant-api       │     │   finetune-api      │     │     eval-api        │             │
│   │                     │     │                     │     │                     │             │
│   │  Span Attrs:        │     │  Span Attrs:        │     │  Span Attrs:        │             │
│   │  - lab.model.*      │     │  - lab.model.*      │     │  - lab.eval.*       │             │
│   │  - genai.usage.*    │     │  - genai.usage.*    │     │  - genai.usage.*    │             │
│   │  - lab.sagemaker.*  │     │  - lab.sagemaker.*  │     │  - lab.sagemaker.*  │             │
│   │                     │     │                     │     │                     │             │
│   │  ┌───────────────┐  │     │  ┌───────────────┐  │     │  ┌───────────────┐  │             │
│   │  │ genai.invoke  │  │     │  │ genai.invoke  │  │     │  │ eval.score    │  │             │
│   │  │   span        │  │     │  │   span        │  │     │  │   span        │  │             │
│   │  └───────────────┘  │     │  └───────────────┘  │     │  └───────────────┘  │             │
│   └─────────────────────┘     └─────────────────────┘     └─────────────────────┘             │
│                                                                                                  │
│                                    ▼                                                            │
│                         ┌─────────────────────┐                                                 │
│                         │   OTEL Collector    │                                                 │
│                         │                     │                                                 │
│                         │  Attribute          │                                                 │
│                         │  Processing:        │                                                 │
│                         │  - k8sattributes    │                                                 │
│                         │  - resource         │                                                 │
│                         └─────────────────────┘                                                 │
│                                    │                                                            │
│              ┌─────────────────────┼─────────────────────┐                                     │
│              ▼                     ▼                     ▼                                     │
│       ┌─────────────┐       ┌─────────────┐       ┌─────────────┐                             │
│       │ Prometheus  │       │    Loki     │       │   Tempo     │                             │
│       │             │       │             │       │             │                             │
│       │ lab_*       │       │ lab.* JSON  │       │ lab.*       │                             │
│       │ genai_*     │       │ fields      │       │ genai.*     │                             │
│       │ metrics     │       │             │       │ spans       │                             │
│       └─────────────┘       └─────────────┘       └─────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Section 0: Naming Rules (Cardinality Control)

### Allowed High-Cardinality Values (Use Carefully)

| Value Type            | Allowed In                 | Notes                         |
| --------------------- | -------------------------- | ----------------------------- |
| `trace_id`, `span_id` | Traces only                | Never on metrics              |
| `experiment.id`       | Bounded, short-lived       | Only if < 100 active          |
| `run.id`              | Bounded                    | Only if < 1000 per day        |
| `model.variant.id`    | Bounded by release cadence | e.g., `awq-7b-v3`             |
| `promptset.id`        | Bounded                    | e.g., `pset-daily-2026-02-23` |

### Forbidden on Metrics (Cardinality Explosions)

| Avoid                         | Use Instead               |
| ----------------------------- | ------------------------- |
| Raw prompts/responses         | `genai.prompt.hash`       |
| Full request IDs if unbounded | `trace_id` in traces only |
| User IDs/emails               | Aggregated cohort labels  |
| Arbitrary free-form strings   | Enums or hashes           |

```python
# Example: Hash prompt for identity without cardinality explosion
import hashlib

def prompt_hash(prompt: str) -> str:
    """Generate stable hash for prompt identity."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]

# Usage in span attributes
span.set_attribute("genai.prompt.hash", prompt_hash(user_prompt))
```

---

## Section 1: Resource Attributes (All Telemetry)

Resource attributes are set **once per process** via the OTel SDK Resource and apply to all telemetry emitted by that process.

### 1.1 Common Attributes (All Services)

| Attribute                | Example                | Required | Notes                       |
| ------------------------ | ---------------------- | -------- | --------------------------- |
| `service.name`           | `gateway`, `quant-api` | ✅       | Unique service identifier   |
| `service.version`        | `1.8.3`                | ✅       | App version from build      |
| `service.instance.id`    | Pod UID                | ✅       | Useful for restart tracking |
| `deployment.environment` | `dev`, `prod`          | ✅       | Environment discriminator   |
| `k8s.cluster.name`       | `llmplatform-dev`      | ✅       | Stable cluster identifier   |
| `k8s.namespace.name`     | `platform`, `quant`    | ✅       | Namespace for filtering     |
| `k8s.pod.name`           | `gateway-6df84...`     | ✅       | OK in logs/traces           |
| `cloud.provider`         | `aws`                  | ✅       | Standard convention         |
| `cloud.region`           | `us-west-2`            | ✅       | Standard convention         |
| `cloud.account.id`       | `123456789012`         | ❌       | Optional                    |
| `telemetry.sdk.name`     | `opentelemetry`        | Auto     | SDK sets automatically      |
| `telemetry.sdk.language` | `python`               | Auto     | SDK sets automatically      |

### 1.2 Team Ownership Attributes

| Attribute         | Example                                 | Required | Notes                |
| ----------------- | --------------------------------------- | -------- | -------------------- |
| `lab.team`        | `platform`, `quant`, `finetune`, `eval` | ✅       | Team ownership       |
| `lab.owner`       | `ml-platform`                           | ❌       | Optional group owner |
| `lab.cost_center` | `ai-lab`                                | ❌       | Cost allocation      |

### Implementation

```python
# services/shared/telemetry.py
import os
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION

def create_resource(service_name: str, namespace: str) -> Resource:
    """Create OTel Resource with standard attributes."""
    return Resource.create({
        # Required service attributes
        SERVICE_NAME: service_name,
        SERVICE_VERSION: os.getenv("SERVICE_VERSION", "0.0.0"),
        "service.instance.id": os.getenv("POD_UID", "unknown"),

        # Environment
        "deployment.environment": os.getenv("ENVIRONMENT", "dev"),

        # Kubernetes
        "k8s.cluster.name": os.getenv("CLUSTER_NAME", "unknown"),
        "k8s.namespace.name": namespace,
        "k8s.pod.name": os.getenv("POD_NAME", "unknown"),

        # Cloud
        "cloud.provider": "aws",
        "cloud.region": os.getenv("AWS_REGION", "us-west-2"),

        # Team ownership
        "lab.team": namespace if namespace in ["quant", "finetune", "eval"] else "platform",
        "lab.owner": "ml-platform",
    })
```

### Kubernetes Deployment Env Vars

```yaml
# Inject pod metadata as environment variables
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
  - name: CLUSTER_NAME
    value: "llmplatform-dev"
  - name: ENVIRONMENT
    value: "dev"
```

---

## Section 2: Gateway Span Schema

The Gateway emits spans that answer: **What route was chosen, why, and what happened?**

### 2.1 Ingress Span (Server)

**Span name**: `http.server.request` (auto-instrumentation) or custom `gateway.route`

| Attribute                   | Example                    | Type    | Notes                                                                              |
| --------------------------- | -------------------------- | ------- | ---------------------------------------------------------------------------------- |
| `lab.request.kind`          | `predict`                  | Enum    | `predict`, `score`, `health`                                                       |
| `lab.route.target.team`     | `quant`                    | Enum    | `quant`, `finetune`, `eval`                                                        |
| `lab.route.target.service`  | `quant-api`                | String  | Stable service name                                                                |
| `lab.route.target.endpoint` | `sagemaker:quant-endpoint` | String  | Target identifier                                                                  |
| `lab.route.policy.id`       | `policy-2026-02-23-a`      | String  | Versioned routing policy                                                           |
| `lab.route.decision`        | `direct`                   | Enum    | `direct`, `fallback`, `deny`                                                       |
| `lab.route.reason`          | `explicit_path`            | Enum    | `explicit_path`, `ab_bucket`, `backend_unready`, `circuit_open`, `quota_guardrail` |
| `lab.ab.enabled`            | `true`                     | Boolean | A/B testing active                                                                 |
| `lab.ab.bucket`             | `B`                        | Enum    | `A`, `B`, etc. (low cardinality)                                                   |
| `lab.model.intent`          | `quantized`                | Enum    | `quantized`, `finetuned`, `evaluator`                                              |
| `lab.timeout.ms`            | `20000`                    | Integer | Gateway timeout to backend                                                         |

### 2.2 Backend Call Span (Client)

**Span name**: `http.client.request` (auto) or `gateway.proxy`

| Attribute                   | Example               | Type    | Notes                                       |
| --------------------------- | --------------------- | ------- | ------------------------------------------- |
| `peer.service`              | `quant-api`           | String  | Standard convention                         |
| `server.address`            | `quant-api.quant.svc` | String  | Auto by HTTP instrumentation                |
| `lab.backend.ready_at_call` | `true`                | Boolean | Backend readiness at dispatch               |
| `lab.backend.retries`       | `1`                   | Integer | Number of retries                           |
| `lab.backend.timeout.ms`    | `8000`                | Integer | Timeout for this call                       |
| `lab.fallback.from`         | `quant`               | String  | Only when fallback occurs                   |
| `lab.fallback.to`           | `finetune`            | String  | Only when fallback occurs                   |
| `error.type`                | `timeout`             | Enum    | `timeout`, `http_5xx`, `connection_refused` |
| `error.message`             | `...`                 | String  | Keep short, no secrets                      |

### Gateway Implementation

```python
# services/gateway/spans.py
from opentelemetry import trace
from typing import Optional

tracer = trace.get_tracer("gateway")


def set_route_attributes(
    span: trace.Span,
    team: str,
    decision: str,
    reason: str,
    policy_id: str,
    ab_bucket: Optional[str] = None,
    timeout_ms: int = 30000
):
    """Set routing attributes on Gateway ingress span."""
    span.set_attribute("lab.request.kind", "predict")
    span.set_attribute("lab.route.target.team", team)
    span.set_attribute("lab.route.target.service", f"{team}-api")
    span.set_attribute("lab.route.target.endpoint", f"sagemaker:{team}-endpoint")
    span.set_attribute("lab.route.policy.id", policy_id)
    span.set_attribute("lab.route.decision", decision)
    span.set_attribute("lab.route.reason", reason)
    span.set_attribute("lab.timeout.ms", timeout_ms)

    # Model intent mapping
    intent_map = {
        "quant": "quantized",
        "finetune": "finetuned",
        "eval": "evaluator"
    }
    span.set_attribute("lab.model.intent", intent_map.get(team, "unknown"))

    # A/B testing
    span.set_attribute("lab.ab.enabled", ab_bucket is not None)
    if ab_bucket:
        span.set_attribute("lab.ab.bucket", ab_bucket)


def set_backend_call_attributes(
    span: trace.Span,
    team: str,
    ready_at_call: bool,
    retries: int = 0,
    timeout_ms: int = 8000,
    fallback_from: Optional[str] = None,
    fallback_to: Optional[str] = None
):
    """Set attributes on backend proxy span."""
    span.set_attribute("peer.service", f"{team}-api")
    span.set_attribute("lab.backend.ready_at_call", ready_at_call)
    span.set_attribute("lab.backend.retries", retries)
    span.set_attribute("lab.backend.timeout.ms", timeout_ms)

    if fallback_from and fallback_to:
        span.set_attribute("lab.fallback.from", fallback_from)
        span.set_attribute("lab.fallback.to", fallback_to)
```

---

## Section 3: Team Service Span Schema

Each team service (quant-api, finetune-api, eval-api) emits spans for inference operations.

### 3.1 Ingress Span (Server)

**Span name**: `http.server.request`

| Attribute                | Example                 | Type   | Notes                                      |
| ------------------------ | ----------------------- | ------ | ------------------------------------------ |
| `lab.team`               | `quant`                 | Enum   | Team identifier                            |
| `lab.request.kind`       | `predict`               | Enum   | Same as gateway                            |
| `lab.gateway.service`    | `gateway`               | String | Upstream caller                            |
| `lab.route.policy.id`    | `policy-...`            | String | Propagated from gateway                    |
| `lab.model.variant.type` | `awq`                   | Enum   | `gptq`, `awq`, `lora`, `base`, `evaluator` |
| `lab.model.variant.id`   | `awq-7b-v3`             | String | Stable release ID                          |
| `lab.model.base.id`      | `llama-2-7b`            | String | Base model identifier                      |
| `lab.model.adapter.id`   | `lora-legal-v5`         | String | Fine-tune only                             |
| `lab.model.task`         | `chat`                  | Enum   | `chat`, `score`, `completion`              |
| `lab.experiment.id`      | `exp-1042`              | String | Optional, only if bounded                  |
| `lab.run.id`             | `run-00017`             | String | Optional, only if bounded                  |
| `lab.promptset.id`       | `pset-daily-2026-02-23` | String | Bounded identifier                         |

### 3.2 Preprocess Span

**Span name**: `llm.preprocess`

| Attribute                  | Example | Type    | Notes                          |
| -------------------------- | ------- | ------- | ------------------------------ |
| `lab.payload.bytes`        | `12876` | Integer | Input payload size             |
| `genai.prompt.tokens`      | `842`   | Integer | Token count after tokenization |
| `lab.prompt.truncated`     | `false` | Boolean | Truncation applied             |
| `lab.safety.input_checked` | `true`  | Boolean | Safety filter ran              |

### 3.3 Inference / SageMaker Span

**Span name**: `genai.invoke` (custom) or `http.client.request` with GenAI attributes

This follows the [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).

| Attribute                     | Example            | Type    | Notes                                 |
| ----------------------------- | ------------------ | ------- | ------------------------------------- |
| `genai.system`                | `aws.sagemaker`    | String  | Stable system identifier              |
| `genai.operation.name`        | `chat.completions` | String  | `chat.completions`, `text_generation` |
| `genai.request.model`         | `awq-7b-v3`        | String  | Requested model                       |
| `genai.response.model`        | `awq-7b-v3`        | String  | If differs, capture                   |
| `genai.usage.input_tokens`    | `842`              | Integer | Input token count                     |
| `genai.usage.output_tokens`   | `311`              | Integer | Output token count                    |
| `genai.usage.total_tokens`    | `1153`             | Integer | Total tokens                          |
| `lab.llm.ttft.ms`             | `220`              | Integer | Time to first token (streaming)       |
| `lab.llm.tpot.ms`             | `18`               | Integer | Time per output token                 |
| `lab.llm.tokens_per_sec`      | `55.2`             | Float   | Generation speed                      |
| `lab.sagemaker.endpoint.name` | `quant-endpoint`   | String  | SageMaker endpoint                    |
| `lab.sagemaker.variant.name`  | `AllTraffic`       | String  | Endpoint variant                      |
| `lab.retry.count`             | `0`                | Integer | Retries performed                     |
| `error.type`                  | `timeout`          | Enum    | `timeout`, `throttle`, `model_error`  |
| `http.status_code`            | `200`              | Integer | Auto-instrumented                     |

### 3.4 Postprocess Span

**Span name**: `llm.postprocess`

| Attribute                   | Example | Type    | Notes             |
| --------------------------- | ------- | ------- | ----------------- |
| `lab.response.format`       | `json`  | String  | Output format     |
| `lab.safety.output_checked` | `true`  | Boolean | Safety filter ran |
| `lab.response.blocked`      | `false` | Boolean | Response filtered |

### 3.5 Eval Scoring Span (Eval Team Only)

**Span name**: `eval.score`

| Attribute                    | Example         | Type    | Notes                  |
| ---------------------------- | --------------- | ------- | ---------------------- |
| `lab.eval.model.id`          | `evaluator-v2`  | String  | Eval model ID          |
| `lab.eval.metric.coherence`  | `0.82`          | Float   | Score (in traces only) |
| `lab.eval.metric.factuality` | `0.71`          | Float   | Score (in traces only) |
| `lab.eval.metric.toxicity`   | `0.03`          | Float   | Score (in traces only) |
| `lab.eval.pass`              | `true`          | Boolean | Pass/fail decision     |
| `lab.eval.threshold.profile` | `daily-gate-v1` | String  | Threshold config       |

> **Note**: Float scores are OK in traces. For metrics, emit them as metric values, not attributes.

### Team Service Implementation

```python
# services/shared/genai_spans.py
from opentelemetry import trace
from typing import Optional
import time

tracer = trace.get_tracer("genai")


class GenAISpanContext:
    """Context manager for GenAI inference spans with timing."""

    def __init__(
        self,
        span_name: str,
        model_variant_type: str,
        model_variant_id: str,
        sagemaker_endpoint: str,
        base_model_id: Optional[str] = None
    ):
        self.span_name = span_name
        self.model_variant_type = model_variant_type
        self.model_variant_id = model_variant_id
        self.sagemaker_endpoint = sagemaker_endpoint
        self.base_model_id = base_model_id
        self.span = None
        self.start_time = None
        self.first_token_time = None

    def __enter__(self):
        self.span = tracer.start_span(self.span_name)
        self.start_time = time.perf_counter()

        # Set initial attributes
        self.span.set_attribute("genai.system", "aws.sagemaker")
        self.span.set_attribute("genai.operation.name", "chat.completions")
        self.span.set_attribute("genai.request.model", self.model_variant_id)
        self.span.set_attribute("lab.model.variant.type", self.model_variant_type)
        self.span.set_attribute("lab.model.variant.id", self.model_variant_id)
        self.span.set_attribute("lab.sagemaker.endpoint.name", self.sagemaker_endpoint)

        if self.base_model_id:
            self.span.set_attribute("lab.model.base.id", self.base_model_id)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.span.set_attribute("error.type", exc_type.__name__)
            self.span.set_attribute("error.message", str(exc_val)[:200])
        self.span.end()

    def record_first_token(self):
        """Call when first token is received (streaming)."""
        self.first_token_time = time.perf_counter()
        ttft_ms = (self.first_token_time - self.start_time) * 1000
        self.span.set_attribute("lab.llm.ttft.ms", int(ttft_ms))

    def record_completion(
        self,
        input_tokens: int,
        output_tokens: int,
        response_model: Optional[str] = None
    ):
        """Record completion metrics."""
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        self.span.set_attribute("genai.usage.input_tokens", input_tokens)
        self.span.set_attribute("genai.usage.output_tokens", output_tokens)
        self.span.set_attribute("genai.usage.total_tokens", input_tokens + output_tokens)

        if response_model:
            self.span.set_attribute("genai.response.model", response_model)

        if output_tokens > 0:
            tpot_ms = duration_ms / output_tokens
            tokens_per_sec = (output_tokens / duration_ms) * 1000
            self.span.set_attribute("lab.llm.tpot.ms", int(tpot_ms))
            self.span.set_attribute("lab.llm.tokens_per_sec", round(tokens_per_sec, 1))


# Usage in team service
async def invoke_sagemaker(prompt: str, config: dict):
    with GenAISpanContext(
        span_name="genai.invoke",
        model_variant_type="awq",
        model_variant_id="awq-7b-v3",
        sagemaker_endpoint="quant-endpoint",
        base_model_id="llama-2-7b"
    ) as ctx:
        # Preprocess span
        with tracer.start_span("llm.preprocess") as pre_span:
            pre_span.set_attribute("lab.payload.bytes", len(prompt.encode()))
            pre_span.set_attribute("lab.safety.input_checked", True)
            # ... tokenize
            pre_span.set_attribute("genai.prompt.tokens", token_count)

        # Call SageMaker
        response = await sagemaker_client.invoke(...)

        # Record completion
        ctx.record_completion(
            input_tokens=842,
            output_tokens=311
        )

        # Postprocess span
        with tracer.start_span("llm.postprocess") as post_span:
            post_span.set_attribute("lab.response.format", "json")
            post_span.set_attribute("lab.safety.output_checked", True)
            post_span.set_attribute("lab.response.blocked", False)

        return response
```

---

## Section 4: Metric Schema

Metrics use **low-cardinality labels only** to prevent cardinality explosions.

### 4.1 Gateway Metrics

#### Counters

```python
# Metric definitions
lab_gateway_requests_total = meter.create_counter(
    "lab_gateway_requests_total",
    description="Total gateway requests"
)
# Labels: target_team, decision, status_code, ab_bucket

lab_gateway_fallback_total = meter.create_counter(
    "lab_gateway_fallback_total",
    description="Total fallback events"
)
# Labels: from_team, to_team, reason

lab_gateway_denied_total = meter.create_counter(
    "lab_gateway_denied_total",
    description="Total denied requests"
)
# Labels: reason
```

#### Histograms

```python
lab_gateway_request_duration_ms = meter.create_histogram(
    "lab_gateway_request_duration_ms",
    description="Gateway request duration",
    unit="ms"
)
# Labels: target_team, decision

lab_gateway_backend_duration_ms = meter.create_histogram(
    "lab_gateway_backend_duration_ms",
    description="Backend call duration",
    unit="ms"
)
# Labels: target_team
```

### 4.2 Team Service Metrics

#### Counters

```python
lab_service_requests_total = meter.create_counter(
    "lab_service_requests_total",
    description="Total service requests"
)
# Labels: team, variant_type, variant_id, status_code

lab_service_sagemaker_errors_total = meter.create_counter(
    "lab_service_sagemaker_errors_total",
    description="SageMaker invocation errors"
)
# Labels: team, variant_id, error_type

lab_service_retries_total = meter.create_counter(
    "lab_service_retries_total",
    description="Total retry attempts"
)
# Labels: team, variant_id
```

#### Histograms

```python
lab_llm_ttft_ms = meter.create_histogram(
    "lab_llm_ttft_ms",
    description="Time to first token (streaming)",
    unit="ms"
)
# Labels: team, variant_id

lab_llm_e2e_duration_ms = meter.create_histogram(
    "lab_llm_e2e_duration_ms",
    description="End-to-end inference duration",
    unit="ms"
)
# Labels: team, variant_id

lab_llm_tpot_ms = meter.create_histogram(
    "lab_llm_tpot_ms",
    description="Time per output token",
    unit="ms"
)
# Labels: team, variant_id
```

#### Gauges

```python
lab_llm_inflight_requests = meter.create_up_down_counter(
    "lab_llm_inflight_requests",
    description="Currently processing requests"
)
# Labels: team

lab_llm_queue_depth = meter.create_observable_gauge(
    "lab_llm_queue_depth",
    description="Request queue depth"
)
# Labels: team
```

### 4.3 Eval Metrics

```python
lab_eval_score = meter.create_histogram(
    "lab_eval_score",
    description="Evaluation metric scores"
)
# Labels: metric (coherence|factuality|toxicity), variant_id, promptset_id

lab_eval_pass_rate = meter.create_counter(
    "lab_eval_pass_rate",
    description="Evaluation pass/fail counts"
)
# Labels: variant_id, promptset_id, profile, result (pass|fail)
```

### Prometheus Recording Rules

```yaml
# prometheus/recording-rules.yaml
groups:
  - name: lab_llm_aggregations
    interval: 30s
    rules:
      # Error rate by team
      - record: lab:error_rate:5m
        expr: |
          sum(rate(lab_service_requests_total{status_code=~"5.."}[5m])) by (team)
          / sum(rate(lab_service_requests_total[5m])) by (team)

      # P95 latency by team
      - record: lab:latency_p95:5m
        expr: |
          histogram_quantile(0.95,
            sum(rate(lab_llm_e2e_duration_ms_bucket[5m])) by (le, team)
          )

      # Tokens per second by variant
      - record: lab:tokens_per_sec:5m
        expr: |
          sum(rate(genai_usage_output_tokens_total[5m])) by (variant_id)
          / sum(rate(lab_llm_e2e_duration_ms_sum[5m])) by (variant_id) * 1000
```

---

## Section 5: Log Schema (Loki-Friendly)

Structured JSON logs with trace correlation.

### Required Fields

| Field                  | Example                      | Required        | Notes              |
| ---------------------- | ---------------------------- | --------------- | ------------------ |
| `severity`             | `INFO`                       | ✅              | Log level          |
| `message`              | `SageMaker invoke completed` | ✅              | Human-readable     |
| `trace_id`             | `abc123...`                  | ✅              | For correlation    |
| `span_id`              | `def456...`                  | ✅              | For correlation    |
| `service.name`         | `quant-api`                  | ✅              | Service identifier |
| `lab.team`             | `quant`                      | ✅              | Team ownership     |
| `lab.model.variant.id` | `awq-7b-v3`                  | When applicable | Model context      |
| `lab.route.policy.id`  | `policy-...`                 | When applicable | Routing context    |
| `http.status_code`     | `200`                        | When applicable | Response code      |
| `error.type`           | `timeout`                    | When error      | Error category     |

### Python Logging Configuration

```python
# services/shared/logging_config.py
import logging
import json
from opentelemetry import trace
from datetime import datetime


class OTelJSONFormatter(logging.Formatter):
    """JSON formatter with OTel trace correlation."""

    def __init__(self, service_name: str, team: str):
        super().__init__()
        self.service_name = service_name
        self.team = team

    def format(self, record: logging.LogRecord) -> str:
        # Get current trace context
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None

        log_dict = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "service.name": self.service_name,
            "lab.team": self.team,
        }

        # Add trace correlation
        if ctx and ctx.is_valid:
            log_dict["trace_id"] = format(ctx.trace_id, "032x")
            log_dict["span_id"] = format(ctx.span_id, "016x")

        # Add extra attributes from record
        if hasattr(record, "lab_attributes"):
            log_dict.update(record.lab_attributes)

        # Add exception info
        if record.exc_info:
            log_dict["error.type"] = record.exc_info[0].__name__
            log_dict["error.message"] = str(record.exc_info[1])

        return json.dumps(log_dict)


def configure_logging(service_name: str, team: str, level: str = "INFO"):
    """Configure JSON logging with OTel correlation."""
    handler = logging.StreamHandler()
    handler.setFormatter(OTelJSONFormatter(service_name, team))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    return root
```

### Log Examples

```json
// Successful inference
{
  "timestamp": "2026-02-23T14:32:01.234Z",
  "severity": "INFO",
  "message": "SageMaker invoke completed",
  "trace_id": "abc123def456...",
  "span_id": "789012345678",
  "service.name": "quant-api",
  "lab.team": "quant",
  "lab.model.variant.id": "awq-7b-v3",
  "http.status_code": 200,
  "genai.usage.total_tokens": 1153
}

// Timeout error
{
  "timestamp": "2026-02-23T14:32:05.567Z",
  "severity": "ERROR",
  "message": "SageMaker invoke timeout",
  "trace_id": "abc123def456...",
  "span_id": "789012345679",
  "service.name": "quant-api",
  "lab.team": "quant",
  "lab.model.variant.id": "awq-7b-v3",
  "error.type": "timeout",
  "lab.sagemaker.endpoint.name": "quant-endpoint"
}
```

> **Security**: Never log raw prompts/responses by default.

---

## Section 6: Optional GenAI Detail Events (Sampled/Debug)

For prompt/response inspection in debug scenarios, use **span events** on sampled traces.

### Event Names

| Event              | Purpose                   | When to Use          |
| ------------------ | ------------------------- | -------------------- |
| `genai.prompt`     | Record prompt details     | Sampled debug traces |
| `genai.completion` | Record completion details | Sampled debug traces |

### Event Attributes

| Attribute                   | Example       | Notes                          |
| --------------------------- | ------------- | ------------------------------ |
| `genai.prompt.hash`         | `a1b2c3d4...` | SHA-256 hash (first 16 chars)  |
| `genai.completion.hash`     | `e5f6g7h8...` | SHA-256 hash (first 16 chars)  |
| `lab.redaction.applied`     | `true`        | Indicates content was redacted |
| `lab.payload.encrypted_ref` | `s3://...`    | Pointer to secure storage      |

### Implementation

```python
# services/shared/debug_events.py
import hashlib
from opentelemetry import trace
from typing import Optional

SAMPLING_RATE = 0.01  # 1% of traces get detail events


def should_sample_details() -> bool:
    """Determine if this request should include detail events."""
    import random
    return random.random() < SAMPLING_RATE


def add_prompt_event(
    span: trace.Span,
    prompt_hash: str,
    encrypted_ref: Optional[str] = None
):
    """Add prompt detail event to span."""
    span.add_event(
        "genai.prompt",
        attributes={
            "genai.prompt.hash": prompt_hash,
            "lab.redaction.applied": True,
            "lab.payload.encrypted_ref": encrypted_ref or "not_stored"
        }
    )


def add_completion_event(
    span: trace.Span,
    completion_hash: str,
    encrypted_ref: Optional[str] = None
):
    """Add completion detail event to span."""
    span.add_event(
        "genai.completion",
        attributes={
            "genai.completion.hash": completion_hash,
            "lab.redaction.applied": True,
            "lab.payload.encrypted_ref": encrypted_ref or "not_stored"
        }
    )


# Usage
def invoke_with_debug_events(prompt: str, ...):
    span = trace.get_current_span()

    if should_sample_details():
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        add_prompt_event(span, prompt_hash)

        # ... invoke model ...

        completion_hash = hashlib.sha256(response.encode()).hexdigest()[:16]
        add_completion_event(span, completion_hash)
```

---

## Section 7: Propagation Headers

### Required Headers (Gateway → Services)

| Header        | Standard          | Purpose                     |
| ------------- | ----------------- | --------------------------- |
| `traceparent` | W3C Trace Context | Trace propagation           |
| `tracestate`  | W3C Trace Context | Vendor-specific trace data  |
| `baggage`     | W3C Baggage       | Request context propagation |

### Baggage Keys (Bounded)

| Key                    | Example               | Notes                  |
| ---------------------- | --------------------- | ---------------------- |
| `lab.route.policy.id`  | `policy-2026-02-23-a` | Routing policy version |
| `lab.ab.bucket`        | `A`                   | A/B test bucket        |
| `lab.experiment.id`    | `exp-1042`            | Only if bounded        |
| `lab.promptset.id`     | `pset-daily`          | Bounded identifier     |
| `lab.model.variant.id` | `awq-7b-v3`           | Only if stable         |

> **Warning**: Keep baggage small. Never include user data, prompts, or unbounded values.

### Implementation

```python
# services/gateway/propagation.py
from opentelemetry import baggage
from opentelemetry.propagate import inject
from typing import Dict, Optional


def create_propagation_headers(
    policy_id: str,
    ab_bucket: Optional[str] = None,
    experiment_id: Optional[str] = None,
    promptset_id: Optional[str] = None,
    variant_id: Optional[str] = None
) -> Dict[str, str]:
    """Create headers with trace context and baggage."""

    # Set baggage values
    ctx = baggage.set_baggage("lab.route.policy.id", policy_id)

    if ab_bucket:
        ctx = baggage.set_baggage("lab.ab.bucket", ab_bucket, context=ctx)
    if experiment_id:
        ctx = baggage.set_baggage("lab.experiment.id", experiment_id, context=ctx)
    if promptset_id:
        ctx = baggage.set_baggage("lab.promptset.id", promptset_id, context=ctx)
    if variant_id:
        ctx = baggage.set_baggage("lab.model.variant.id", variant_id, context=ctx)

    # Inject trace context + baggage into headers
    headers = {}
    inject(headers, context=ctx)

    return headers


# Usage in gateway
async def proxy_to_team(team: str, request_body: dict):
    headers = create_propagation_headers(
        policy_id="policy-2026-02-23-a",
        ab_bucket="B",
        variant_id="awq-7b-v3"
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{team}-api.{team}.svc/predict",
            json=request_body,
            headers=headers
        )
```

---

## Section 8: Span Checklist by Component

### Gateway Must Emit (Every Request)

| Attribute                | Required       | Span         |
| ------------------------ | -------------- | ------------ |
| `lab.route.target.team`  | ✅             | Ingress      |
| `lab.route.decision`     | ✅             | Ingress      |
| `lab.route.reason`       | ✅             | Ingress      |
| `lab.route.policy.id`    | ✅             | Ingress      |
| `lab.ab.bucket`          | If A/B enabled | Ingress      |
| `lab.backend.retries`    | ✅             | Backend call |
| `lab.backend.timeout.ms` | ✅             | Backend call |

### Team Service Must Emit (Every Request)

| Attribute                     | Required     | Span         |
| ----------------------------- | ------------ | ------------ |
| `lab.model.variant.type`      | ✅           | Ingress      |
| `lab.model.variant.id`        | ✅           | Ingress      |
| `genai.usage.input_tokens`    | ✅           | genai.invoke |
| `genai.usage.output_tokens`   | ✅           | genai.invoke |
| `lab.llm.ttft.ms`             | If streaming | genai.invoke |
| `lab.llm.tpot.ms`             | If streaming | genai.invoke |
| `lab.sagemaker.endpoint.name` | ✅           | genai.invoke |
| `error.type`                  | On errors    | Any          |

---

## Section 9: Grafana Dashboard Queries

### Request Volume by Team

```promql
sum(rate(lab_gateway_requests_total[5m])) by (target_team)
```

### Error Rate by Variant

```promql
sum(rate(lab_service_requests_total{status_code=~"5.."}[5m])) by (variant_id)
/ sum(rate(lab_service_requests_total[5m])) by (variant_id)
```

### P95 Latency by Model Type

```promql
histogram_quantile(0.95,
  sum(rate(lab_llm_e2e_duration_ms_bucket[5m])) by (le, variant_type)
)
```

### A/B Bucket Distribution

```promql
sum(increase(lab_gateway_requests_total[1h])) by (ab_bucket)
```

### Token Throughput

```promql
sum(rate(genai_usage_output_tokens_total[5m])) by (team)
```

### Loki: Errors with Trace Correlation

```logql
{service_name=~"quant-api|finetune-api|eval-api"}
| json
| severity="ERROR"
| line_format "{{.trace_id}} {{.error_type}}: {{.message}}"
```

### Tempo: Trace Search by Variant

```
{ resource.service.name="quant-api" && span.lab.model.variant.id="awq-7b-v3" }
```

---

## Implementation Checklist

### Resource Attributes

- [ ] All services set `service.name`, `service.version`, `service.instance.id`
- [ ] All services set `deployment.environment`, `k8s.*` attributes
- [ ] All services set `lab.team` ownership attribute
- [ ] Kubernetes deployments inject `POD_NAME`, `POD_UID` env vars

### Gateway Spans

- [ ] Ingress span includes all `lab.route.*` attributes
- [ ] Backend call span includes retry/timeout attributes
- [ ] A/B bucket recorded when enabled
- [ ] Fallback attributes set when fallback occurs

### Team Service Spans

- [ ] `llm.preprocess` span with token count
- [ ] `genai.invoke` span with GenAI semantic conventions
- [ ] `llm.postprocess` span with safety check attributes
- [ ] All `genai.usage.*` token attributes present

### Metrics

- [ ] Gateway counters: `lab_gateway_requests_total`, `lab_gateway_fallback_total`
- [ ] Gateway histograms: `lab_gateway_request_duration_ms`
- [ ] Service counters: `lab_service_requests_total`, `lab_service_sagemaker_errors_total`
- [ ] Service histograms: `lab_llm_e2e_duration_ms`, `lab_llm_ttft_ms`
- [ ] Eval metrics: `lab_eval_score`, `lab_eval_pass_rate`

### Logs

- [ ] JSON format with `trace_id`, `span_id` correlation
- [ ] All logs include `service.name`, `lab.team`
- [ ] Error logs include `error.type`
- [ ] No raw prompts/responses in logs

### Propagation

- [ ] W3C Trace Context (`traceparent`, `tracestate`) propagated
- [ ] Baggage includes `lab.route.policy.id`
- [ ] Baggage limited to bounded values only

### Verification

- [ ] Traces visible in Tempo with full span tree
- [ ] Logs correlate to traces via `trace_id`
- [ ] Metrics queryable in Prometheus
- [ ] Grafana dashboards render correctly
