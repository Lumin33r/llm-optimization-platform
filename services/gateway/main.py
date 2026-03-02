"""Gateway API - routes requests to team SageMaker wrapper services."""

import os
import time
import uuid
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from opentelemetry import trace

from routing import Router
from shared.telemetry import setup_telemetry
from spans import set_route_attributes, set_backend_call_attributes
from propagation import create_propagation_headers
from ops_api import router as ops_router

app = FastAPI(title="Gateway API")

# CORS — allow Grafana (localhost:3000) to call the gateway (localhost:8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your Grafana domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the ops API router (/ops/services, /ops/health, /ops/stats, /ops/test)
app.include_router(ops_router)

tracer, meter = setup_telemetry(app, "gateway", "platform")


# --------------- Health endpoints ---------------
@app.get("/startup")
async def startup():
    """Startup probe - returns 200 once app is alive."""
    return {"status": "started", "service": "gateway"}


@app.get("/health")
async def health():
    """Liveness probe - returns 200 if event loop is responsive."""
    return {"status": "healthy", "service": "gateway"}


@app.get("/ready")
async def ready():
    """Readiness probe - returns 200 if ready for traffic."""
    return {"status": "ready", "service": "gateway"}


# Initialize router from config
ROUTE_TABLE = os.getenv("ROUTE_TABLE", "{}")
router = Router(ROUTE_TABLE)

# HTTP client
http_client = httpx.AsyncClient(timeout=60.0)

# Metrics (design-08 §4 naming)
request_counter = meter.create_counter("lab_gateway_requests_total")
fallback_counter = meter.create_counter("lab_gateway_fallback_total")
latency_histogram = meter.create_histogram("lab_gateway_request_duration_ms")


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

    # Get current span and add route attributes (design-08 §2)
    current_span = trace.get_current_span()
    policy_id = route.policy_id if hasattr(route, "policy_id") else "default"
    set_route_attributes(
        current_span,
        team=team,
        decision="routed",
        reason="path_match",
        policy_id=policy_id,
        ab_bucket=variant,
    )

    # Forward request
    try:
        body = await request.json()

        # Propagate trace context + baggage (design-08 §7)
        headers = create_propagation_headers(
            policy_id=policy_id,
            ab_bucket=variant,
        )
        headers["X-Correlation-ID"] = correlation_id
        headers["Content-Type"] = "application/json"
        if variant:
            headers["X-AB-Variant"] = variant

        # Backend call with span attributes (design-08 §2)
        with tracer.start_as_current_span("backend_call") as backend_span:
            set_backend_call_attributes(
                backend_span,
                team=team,
                ready_at_call=True,
                timeout_ms=route.timeout_ms,
            )

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
