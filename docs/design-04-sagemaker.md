# Design Document 4: Multi-Endpoint SageMaker Integration

## Overview

This document defines the SageMaker integration layer for the LLM Optimization Platform. Each team has a dedicated SageMaker endpoint and a FastAPI wrapper service.

**Key Design Decisions**:

- Each team wrapper exposes a uniform contract (`GET /health`, `/ready`, `/startup`; `POST /predict`)
- Gateway routes requests using explicit `route_table` configuration
- Correlation IDs propagate through the entire call chain
- A/B routing supported via variant weights and response headers
- Baseline model available for comparisons (see [design-10-models.md](design-10-models.md))

---

## Quick Start (Implementation Order)

```bash
# 1. Prerequisites (after design-02 kubectl configured)
# Ensure IRSA roles are created (design-01)

# 2. Deploy team services in order
kubectl apply -k k8s/base/quant-api/
kubectl apply -k k8s/base/finetune-api/
kubectl apply -k k8s/base/eval-api/

# 3. Deploy gateway with route table
kubectl apply -k k8s/base/gateway/

# 4. Verify routing works
curl -X POST "http://gateway/api/quant/predict" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test", "max_tokens": 5}'
```

**Depends On**: [design-02-kubernetes.md](design-02-kubernetes.md), [design-10-models.md](design-10-models.md) (baseline)
**Feeds Into**: [design-06-dashboard.md](design-06-dashboard.md) (ops API)

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                                │
│   External Request                                                                             │
│   POST /api/quant/predict                                                                      │
│   Headers: X-Correlation-ID: req-123                                                           │
│                                                                                                │
└──────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   Gateway (platform)                                          │
│                                                                                               │
│   route_table:                                                                                │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ quant:                                                                               │   │
│   │   url: http://quant-api.quant.svc.cluster.local                                     │   │
│   │   timeout_ms: 30000                                                                  │   │
│   │                                                                                      │   │
│   │ finetune:                                                                            │   │
│   │   url: http://finetune-api.finetune.svc.cluster.local                               │   │
│   │   timeout_ms: 60000                                                                  │   │
│   │   ab_variants:                                                                       │   │
│   │     lora-v1: {weight: 80}                                                           │   │
│   │     lora-v2: {weight: 20}                                                           │   │
│   │                                                                                      │   │
│   │ eval:                                                                                │   │
│   │   url: http://eval-api.eval.svc.cluster.local                                       │   │
│   │   timeout_ms: 45000                                                                  │   │
│   │                                                                                      │   │
│   │ baseline:   # NEW: Baseline model for comparisons (design-10)                        │   │
│   │   url: http://mistral-7b-baseline.llm-baseline.svc.cluster.local:8000               │   │
│   │   timeout_ms: 30000                                                                  │   │
│   │   path_prefix: /v1/chat/completions                                                  │   │
│   │   openai_compatible: true                                                            │   │
│   └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                               │
└─────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
┌───────────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────────┐
│     quant-api (quant)     │ │   finetune-api (finetune) │ │     eval-api (eval)       │
│                           │ │                           │ │                           │
│ Endpoints:                │ │ Endpoints:                │ │ Endpoints:                │
│  GET  /health             │ │  GET  /health             │ │  GET  /health             │
│  GET  /ready              │ │  GET  /ready              │ │  GET  /ready              │
│  GET  /startup            │ │  GET  /startup            │ │  GET  /startup            │
│  POST /predict            │ │  POST /predict            │ │  POST /predict            │
│                           │ │                           │ │                           │
│ SageMaker Endpoint:       │ │ SageMaker Endpoint:       │ │ SageMaker Endpoint:       │
│  quant-endpoint           │ │  finetune-endpoint        │ │  eval-endpoint            │
│  (GPTQ/AWQ models)        │ │  (LoRA adapters)          │ │  (Evaluation scoring)     │
└───────────────┬───────────┘ └───────────────┬───────────┘ └───────────────┬───────────┘
                │                             │                             │
                ▼                             ▼                             ▼
┌───────────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────────┐
│   SageMaker: quant-ep     │ │ SageMaker: finetune-ep    │ │   SageMaker: eval-ep      │
│                           │ │                           │ │                           │
│   ml.g5.xlarge            │ │   ml.g5.2xlarge           │ │   ml.g5.xlarge            │
│   GPTQ 4-bit models       │ │   LoRA fine-tuned models  │ │   Scoring/eval models     │
└───────────────────────────┘ └───────────────────────────┘ └───────────────────────────┘
```

---

## Team Wrapper Service Contract

All team services must implement this uniform API contract:

| Endpoint   | Method | Purpose                           | Response Code   |
| ---------- | ------ | --------------------------------- | --------------- |
| `/health`  | GET    | Liveness - process alive          | 200 / 500       |
| `/ready`   | GET    | Readiness - ready for traffic     | 200 / 503       |
| `/startup` | GET    | Startup - initialization complete | 200 / 503       |
| `/predict` | POST   | Inference request                 | 200 / 4xx / 5xx |

### Health/Ready/Startup Semantics

```python
# services/shared/health.py
"""Health check implementations for team services."""

from enum import Enum
import asyncio
from typing import Optional

class ServiceState(Enum):
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthChecker:
    """Manages service health state."""

    def __init__(self, sagemaker_client):
        self.state = ServiceState.STARTING
        self.sagemaker_client = sagemaker_client
        self.last_sagemaker_check: Optional[float] = None
        self.sagemaker_reachable: bool = False

    async def startup_check(self) -> bool:
        """
        Check if service startup is complete.
        Returns True when:
        - Configuration loaded
        - SageMaker endpoint is reachable (initial check)
        - All dependencies initialized
        """
        if self.state == ServiceState.STARTING:
            # Verify SageMaker endpoint exists and is InService
            try:
                endpoint_ok = await self.sagemaker_client.check_endpoint_status()
                if endpoint_ok:
                    self.state = ServiceState.READY
                    self.sagemaker_reachable = True
                    return True
            except Exception:
                return False
        return self.state != ServiceState.STARTING

    async def readiness_check(self) -> bool:
        """
        Check if service is ready to handle traffic.
        Returns True when:
        - Startup complete
        - SageMaker endpoint InService (recent check)
        - No circuit breaker open
        """
        if self.state in (ServiceState.STARTING, ServiceState.UNHEALTHY):
            return False

        # Periodic SageMaker health verification
        import time
        now = time.time()
        if self.last_sagemaker_check is None or (now - self.last_sagemaker_check) > 30:
            self.sagemaker_reachable = await self.sagemaker_client.check_endpoint_status()
            self.last_sagemaker_check = now

        return self.sagemaker_reachable and self.state == ServiceState.READY

    async def liveness_check(self) -> bool:
        """
        Check if service is alive (not deadlocked).
        Returns True when:
        - Event loop responsive
        - Memory within limits
        - No deadlock detected
        """
        # Simple async responsiveness check
        try:
            await asyncio.sleep(0)  # Yield to event loop
            return True
        except Exception:
            return False
```

---

## Team Service Implementation

### Base Service Structure

```
services/
├── shared/
│   ├── __init__.py
│   ├── health.py              # Health check utilities
│   ├── telemetry.py           # OTEL instrumentation
│   ├── sagemaker_client.py    # SageMaker wrapper
│   └── models.py              # Pydantic models
├── gateway/
│   ├── __init__.py
│   ├── main.py
│   ├── routes.py
│   ├── routing.py             # Route table + A/B logic
│   └── ops_api.py             # Operations endpoints
├── quant-api/
│   ├── __init__.py
│   ├── main.py
│   └── Dockerfile
├── finetune-api/
│   ├── __init__.py
│   ├── main.py
│   └── Dockerfile
└── eval-api/
    ├── __init__.py
    ├── main.py
    └── Dockerfile
```

### SageMaker Client

```python
# services/shared/sagemaker_client.py
"""SageMaker endpoint client with OTEL tracing."""

import os
import json
import asyncio
from typing import Optional, Dict, Any
import boto3
from botocore.config import Config
from opentelemetry import trace


class SageMakerClient:
    """Async SageMaker endpoint client with timeout and error handling."""

    def __init__(
        self,
        endpoint_name: str,
        timeout_ms: int = 30000,
        enable_fallback: bool = False,
        fallback_response: Optional[Dict] = None
    ):
        self.endpoint_name = endpoint_name
        self.timeout_seconds = timeout_ms / 1000
        self.enable_fallback = enable_fallback
        self.fallback_response = fallback_response or {"error": "fallback_response"}

        # Configure boto3 with timeout
        config = Config(
            read_timeout=self.timeout_seconds,
            connect_timeout=5,
            retries={'max_attempts': 1}
        )
        self.sagemaker_runtime = boto3.client(
            'sagemaker-runtime',
            region_name=os.getenv('AWS_REGION', 'us-west-2'),
            config=config
        )
        self.sagemaker = boto3.client('sagemaker')
        self.tracer = trace.get_tracer(__name__)

    async def check_endpoint_status(self) -> bool:
        """Check if SageMaker endpoint is InService."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.sagemaker.describe_endpoint(EndpointName=self.endpoint_name)
            )
            return response['EndpointStatus'] == 'InService'
        except Exception:
            return False

    async def invoke(
        self,
        payload: Dict[str, Any],
        correlation_id: str,
        variant: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke SageMaker endpoint with tracing.

        Args:
            payload: Request payload (will be JSON serialized)
            correlation_id: Request correlation ID for tracing
            variant: Optional production variant name (for A/B testing)

        Returns:
            Parsed JSON response from model

        Raises:
            TimeoutError: If request exceeds timeout_ms
            SageMakerError: If SageMaker returns an error
        """
        with self.tracer.start_as_current_span("sagemaker.invoke_endpoint") as span:
            span.set_attribute("sagemaker.endpoint", self.endpoint_name)
            span.set_attribute("correlation_id", correlation_id)
            if variant:
                span.set_attribute("sagemaker.variant", variant)

            try:
                loop = asyncio.get_event_loop()

                invoke_params = {
                    'EndpointName': self.endpoint_name,
                    'Body': json.dumps(payload),
                    'ContentType': 'application/json',
                    'Accept': 'application/json'
                }

                if variant:
                    invoke_params['TargetVariant'] = variant

                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self.sagemaker_runtime.invoke_endpoint(**invoke_params)
                    ),
                    timeout=self.timeout_seconds
                )

                result = json.loads(response['Body'].read().decode())
                span.set_attribute("sagemaker.success", True)
                return result

            except asyncio.TimeoutError:
                span.set_attribute("sagemaker.error", "timeout")
                span.set_attribute("sagemaker.timeout_ms", self.timeout_seconds * 1000)

                if self.enable_fallback:
                    span.set_attribute("sagemaker.fallback_used", True)
                    return self.fallback_response
                else:
                    raise TimeoutError(
                        f"SageMaker endpoint {self.endpoint_name} timed out "
                        f"after {self.timeout_seconds}s"
                    )

            except Exception as e:
                span.set_attribute("sagemaker.error", str(e))
                span.set_attribute("sagemaker.error_type", type(e).__name__)
                raise


class SageMakerError(Exception):
    """SageMaker invocation error."""
    pass
```

### Team Service (Example: quant-api)

```python
# services/quant-api/main.py
"""Quantization Team API - SageMaker wrapper for GPTQ/AWQ models."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uuid

from shared.health import HealthChecker
from shared.sagemaker_client import SageMakerClient
from shared.telemetry import setup_telemetry


# Request/Response Models
class PredictRequest(BaseModel):
    """Prediction request payload."""
    prompt: str
    max_tokens: int = 256
    temperature: float = 0.7
    model_params: Optional[dict] = None


class PredictResponse(BaseModel):
    """Prediction response."""
    output: str
    model_version: str
    latency_ms: float
    correlation_id: str


# Lifespan for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    # Startup
    app.state.sagemaker = SageMakerClient(
        endpoint_name=os.getenv("SAGEMAKER_ENDPOINT_NAME", "quant-endpoint"),
        timeout_ms=int(os.getenv("SAGEMAKER_TIMEOUT_MS", "30000")),
        enable_fallback=os.getenv("ENABLE_FALLBACK", "false").lower() == "true"
    )
    app.state.health = HealthChecker(app.state.sagemaker)

    yield

    # Cleanup
    pass


# Create app
app = FastAPI(
    title="Quant API",
    description="Quantization team SageMaker wrapper",
    lifespan=lifespan
)

# Setup telemetry
tracer, meter = setup_telemetry(app, "quant-api", "quant")

# Metrics
predict_counter = meter.create_counter("quant_api.predictions")
predict_latency = meter.create_histogram("quant_api.latency_ms")


# Health Endpoints
@app.get("/startup")
async def startup():
    """Startup probe - returns 200 when initialization complete."""
    if await app.state.health.startup_check():
        return {"status": "started", "service": "quant-api"}
    raise HTTPException(status_code=503, detail="Service starting")


@app.get("/health")
async def health():
    """Liveness probe - returns 200 if process is alive."""
    if await app.state.health.liveness_check():
        return {"status": "healthy", "service": "quant-api"}
    raise HTTPException(status_code=500, detail="Service unhealthy")


@app.get("/ready")
async def ready():
    """Readiness probe - returns 200 if ready for traffic."""
    if await app.state.health.readiness_check():
        return {"status": "ready", "service": "quant-api"}
    raise HTTPException(status_code=503, detail="Service not ready")


# Prediction Endpoint
@app.post("/predict", response_model=PredictResponse)
async def predict(
    request: PredictRequest,
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """
    Run inference through SageMaker endpoint.

    Headers:
        X-Correlation-ID: Request correlation ID (generated if not provided)

    Returns:
        PredictResponse with model output and metadata
    """
    import time
    start_time = time.time()

    # Generate correlation ID if not provided
    correlation_id = x_correlation_id or str(uuid.uuid4())

    # Build SageMaker payload
    payload = {
        "inputs": request.prompt,
        "parameters": {
            "max_new_tokens": request.max_tokens,
            "temperature": request.temperature,
            **(request.model_params or {})
        }
    }

    try:
        # Invoke SageMaker
        result = await app.state.sagemaker.invoke(
            payload=payload,
            correlation_id=correlation_id
        )

        latency_ms = (time.time() - start_time) * 1000

        # Record metrics
        predict_counter.add(1, {"status": "success"})
        predict_latency.record(latency_ms)

        return PredictResponse(
            output=result.get("generated_text", result.get("output", "")),
            model_version=result.get("model_version", "unknown"),
            latency_ms=latency_ms,
            correlation_id=correlation_id
        )

    except TimeoutError as e:
        predict_counter.add(1, {"status": "timeout"})
        raise HTTPException(
            status_code=504,
            detail={
                "error": "sagemaker_timeout",
                "message": str(e),
                "correlation_id": correlation_id
            }
        )
    except Exception as e:
        predict_counter.add(1, {"status": "error"})
        raise HTTPException(
            status_code=500,
            detail={
                "error": "prediction_failed",
                "message": str(e),
                "correlation_id": correlation_id
            }
        )


# Error handlers
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": str(exc),
            "service": "quant-api"
        }
    )
```

---

## Gateway Routing

### Route Table Configuration

```python
# services/gateway/routing.py
"""Gateway routing with A/B testing support."""

import os
import json
import random
from typing import Optional, Dict, Any
from dataclasses import dataclass
from opentelemetry import trace


@dataclass
class RouteConfig:
    """Configuration for a single route."""
    url: str
    timeout_ms: int
    ab_variants: Optional[Dict[str, Dict]] = None  # {variant: {weight: int}}


class Router:
    """Routes requests to team services with A/B support."""

    def __init__(self, route_table_json: str):
        self.routes: Dict[str, RouteConfig] = {}
        self._parse_route_table(route_table_json)
        self.tracer = trace.get_tracer(__name__)

    def _parse_route_table(self, json_str: str):
        """Parse route table from JSON config."""
        config = json.loads(json_str)
        for team, settings in config.items():
            self.routes[team] = RouteConfig(
                url=settings["url"],
                timeout_ms=settings.get("timeout_ms", 30000),
                ab_variants=settings.get("ab_variants")
            )

    def get_route(self, team: str) -> Optional[RouteConfig]:
        """Get route configuration for a team."""
        return self.routes.get(team)

    def select_variant(self, team: str) -> Optional[str]:
        """
        Select A/B variant based on configured weights.

        Returns:
            Selected variant name, or None if no A/B configured
        """
        route = self.routes.get(team)
        if not route or not route.ab_variants:
            return None

        # Calculate total weight
        variants = route.ab_variants
        total_weight = sum(v.get("weight", 0) for v in variants.values())
        if total_weight == 0:
            return None

        # Random selection
        rand = random.randint(1, total_weight)
        cumulative = 0
        for variant_name, variant_config in variants.items():
            cumulative += variant_config.get("weight", 0)
            if rand <= cumulative:
                return variant_name

        return list(variants.keys())[0]  # Fallback to first variant

    def get_available_teams(self) -> list:
        """Return list of available team routes."""
        return list(self.routes.keys())


# Gateway main with routing
# services/gateway/main.py
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import httpx
import uuid
import time

from routing import Router
from shared.telemetry import setup_telemetry

app = FastAPI(title="Gateway API")
tracer, meter = setup_telemetry(app, "gateway", "platform")

# Initialize router from config
ROUTE_TABLE = os.getenv("ROUTE_TABLE", "{}")
router = Router(ROUTE_TABLE)

# HTTP client
http_client = httpx.AsyncClient(timeout=60.0)

# Metrics
request_counter = meter.create_counter("gateway.requests")
latency_histogram = meter.create_histogram("gateway.latency_ms")


@app.post("/api/{team}/predict")
async def route_predict(
    team: str,
    request: Request,
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """
    Route prediction request to team service.

    Path:
        team: Target team (quant, finetune, eval)

    Headers:
        X-Correlation-ID: Correlation ID (generated if not provided)

    Response Headers:
        X-Correlation-ID: Echo correlation ID
        X-Route-Team: Team that handled request
        X-Route-Variant: A/B variant selected (if applicable)
    """
    start_time = time.time()
    correlation_id = x_correlation_id or str(uuid.uuid4())

    # Get route config
    route = router.get_route(team)
    if not route:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_team", "team": team}
        )

    # Select A/B variant if configured
    variant = router.select_variant(team)

    # Get current span and add attributes
    current_span = trace.get_current_span()
    current_span.set_attribute("team", team)
    current_span.set_attribute("correlation_id", correlation_id)
    if variant:
        current_span.set_attribute("ab_variant", variant)

    # Forward request
    try:
        body = await request.json()

        headers = {
            "X-Correlation-ID": correlation_id,
            "Content-Type": "application/json"
        }
        if variant:
            headers["X-AB-Variant"] = variant

        response = await http_client.post(
            f"{route.url}/predict",
            json=body,
            headers=headers,
            timeout=route.timeout_ms / 1000
        )

        latency_ms = (time.time() - start_time) * 1000

        # Record metrics
        request_counter.add(1, {"team": team, "status": "success"})
        latency_histogram.record(latency_ms, {"team": team})

        # Build response with tracking headers
        result = response.json()
        return JSONResponse(
            content=result,
            headers={
                "X-Correlation-ID": correlation_id,
                "X-Route-Team": team,
                "X-Route-Variant": variant or "default",
                "X-Latency-Ms": str(int(latency_ms))
            }
        )

    except httpx.TimeoutException:
        request_counter.add(1, {"team": team, "status": "timeout"})
        raise HTTPException(
            status_code=504,
            detail={
                "error": "upstream_timeout",
                "team": team,
                "correlation_id": correlation_id
            }
        )
    except Exception as e:
        request_counter.add(1, {"team": team, "status": "error"})
        raise HTTPException(
            status_code=502,
            detail={
                "error": "upstream_error",
                "team": team,
                "message": str(e),
                "correlation_id": correlation_id
            }
        )
```

---

## A/B Routing Configuration

### ConfigMap Example

```yaml
# Gateway ConfigMap with A/B routing
apiVersion: v1
kind: ConfigMap
metadata:
  name: gateway-config
  namespace: platform
data:
  ROUTE_TABLE: |
    {
      "quant": {
        "url": "http://quant-api.quant.svc.cluster.local",
        "timeout_ms": 30000
      },
      "finetune": {
        "url": "http://finetune-api.finetune.svc.cluster.local",
        "timeout_ms": 60000,
        "ab_variants": {
          "lora-v1": {"weight": 80},
          "lora-v2": {"weight": 20}
        }
      },
      "eval": {
        "url": "http://eval-api.eval.svc.cluster.local",
        "timeout_ms": 45000
      }
    }
```

### A/B Response Headers

Every response includes headers for variant tracking:

| Header             | Description                           |
| ------------------ | ------------------------------------- |
| `X-Correlation-ID` | Request correlation ID                |
| `X-Route-Team`     | Team that handled the request         |
| `X-Route-Variant`  | A/B variant selected (or "default")   |
| `X-Latency-Ms`     | Total gateway latency in milliseconds |

---

## Controlled Failure Scenario: SageMaker Timeout

### Scenario Description

Test SageMaker timeout handling when endpoint is slow or unresponsive.

### Expected Behavior

1. Request arrives at team service
2. Team service calls SageMaker with configured timeout
3. SageMaker does not respond within timeout
4. Two possible outcomes:
   - **ENABLE_FALLBACK=false**: Return 504 Gateway Timeout error
   - **ENABLE_FALLBACK=true**: Return fallback response

### Test Implementation

```python
# Test: SageMaker timeout handling
import httpx
import pytest

@pytest.mark.asyncio
async def test_sagemaker_timeout_error_propagation():
    """Test that SageMaker timeout returns 504 when fallback disabled."""

    # Configure service with short timeout and no fallback
    # (Via environment or mock)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://gateway/api/quant/predict",
            json={"prompt": "test", "max_tokens": 100},
            headers={"X-Correlation-ID": "test-timeout-001"}
        )

        # Should get 504 Gateway Timeout
        assert response.status_code == 504

        data = response.json()
        assert data["error"] == "upstream_timeout"
        assert "correlation_id" in data


@pytest.mark.asyncio
async def test_sagemaker_timeout_with_fallback():
    """Test that SageMaker timeout returns fallback when enabled."""

    # Configure service with fallback enabled
    # Set ENABLE_FALLBACK=true

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://gateway/api/quant/predict",
            json={"prompt": "test", "max_tokens": 100},
            headers={"X-Correlation-ID": "test-fallback-001"}
        )

        # Should get 200 with fallback response
        assert response.status_code == 200

        data = response.json()
        assert "fallback" in data or data.get("is_fallback") == True
```

---

## SageMaker Endpoint Terraform (Reference)

```hcl
# infra/modules/sagemaker_endpoints/main.tf

variable "endpoints" {
  type = map(object({
    model_name     = string
    instance_type  = string
    instance_count = number
    model_data_url = string  # S3 path to model artifacts
    variants = optional(list(object({
      name   = string
      weight = number
    })))
  }))
}

resource "aws_sagemaker_model" "team" {
  for_each = var.endpoints

  name               = "${var.project}-${var.environment}-${each.key}-model"
  execution_role_arn = var.sagemaker_role_arn

  primary_container {
    image          = var.inference_image
    model_data_url = each.value.model_data_url
    environment = {
      MODEL_NAME = each.value.model_name
    }
  }
}

resource "aws_sagemaker_endpoint_configuration" "team" {
  for_each = var.endpoints

  name = "${var.project}-${var.environment}-${each.key}-config"

  dynamic "production_variant" {
    for_each = each.value.variants != null ? each.value.variants : [
      { name = "default", weight = 100 }
    ]
    content {
      variant_name           = production_variant.value.name
      model_name             = aws_sagemaker_model.team[each.key].name
      initial_instance_count = each.value.instance_count
      instance_type          = each.value.instance_type
      initial_variant_weight = production_variant.value.weight
    }
  }
}

resource "aws_sagemaker_endpoint" "team" {
  for_each = var.endpoints

  name                 = "${var.project}-${var.environment}-${each.key}-endpoint"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.team[each.key].name

  tags = var.tags
}

output "endpoint_names" {
  value = { for k, v in aws_sagemaker_endpoint.team : k => v.name }
}
```

---

## Implementation Checklist

- [ ] Implement shared SageMaker client with timeout handling
- [ ] Implement health check utilities (startup/liveness/readiness)
- [ ] Create quant-api service with full probe pattern
- [ ] Create finetune-api service with A/B variant support
- [ ] Create eval-api service
- [ ] Implement Gateway router with route table
- [ ] Configure A/B variant selection in Gateway
- [ ] Add correlation ID propagation through call chain
- [ ] Add response headers (X-Route-Team, X-Route-Variant)
- [ ] Test SageMaker timeout with fallback disabled
- [ ] Test SageMaker timeout with fallback enabled
- [ ] Verify OTEL traces span Gateway → Team → SageMaker
- [ ] Deploy and verify all three team endpoints
