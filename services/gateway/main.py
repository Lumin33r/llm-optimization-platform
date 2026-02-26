"""Gateway API - routes requests to team SageMaker wrapper services."""

import os
import time
import uuid
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import httpx
from opentelemetry import trace

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
