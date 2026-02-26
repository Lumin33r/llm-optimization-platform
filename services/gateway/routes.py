"""FastAPI routes for gateway - /api/{team}/predict etc."""

import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import httpx
from opentelemetry import trace

from routing import Router

router = APIRouter()

# Initialize Router from env config
ROUTE_TABLE = os.getenv("ROUTE_TABLE", "{}")
route_manager = Router(ROUTE_TABLE)

# HTTP client for forwarding requests
http_client = httpx.AsyncClient(timeout=60.0)


@router.post("/api/{team}/predict")
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
    route = route_manager.get_route(team)
    if not route:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_team", "team": team}
        )

    # Select A/B variant if configured
    variant = route_manager.select_variant(team)

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
        raise HTTPException(
            status_code=504,
            detail={
                "error": "upstream_timeout",
                "team": team,
                "correlation_id": correlation_id
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "upstream_error",
                "team": team,
                "message": str(e),
                "correlation_id": correlation_id
            }
        )
