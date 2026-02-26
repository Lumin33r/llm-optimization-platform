"""Operations API for the LLM Platform dashboard."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import httpx
import asyncio
import os
from datetime import datetime, timedelta

router = APIRouter(prefix="/ops", tags=["operations"])


# Response Models
class ServiceInfo(BaseModel):
    """Information about a registered service."""
    name: str
    namespace: str
    url: str
    version: str
    deployed_at: Optional[str] = None
    image_tag: Optional[str] = None


class HealthStatus(BaseModel):
    """Health status for a team/service."""
    team: str
    status: str  # "healthy", "degraded", "unhealthy"
    ready_pods: int
    total_pods: int
    last_check: str


class PlatformStats(BaseModel):
    """Platform-wide statistics."""
    total_requests_24h: int
    error_rate_percent: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    requests_by_team: Dict[str, int]
    errors_by_team: Dict[str, int]
    window_start: str
    window_end: str


class TestRequest(BaseModel):
    """Test prediction request."""
    team: str
    prompt: str = "Test prompt for health check"
    max_tokens: int = 10


class TestResponse(BaseModel):
    """Test prediction response."""
    correlation_id: str
    team: str
    status: str  # "success", "error", "timeout"
    latency_ms: float
    response: Optional[Dict] = None
    error: Optional[str] = None


# Service registry (populated from route_table)
from routing import router as route_router


@router.get("/services", response_model=List[ServiceInfo])
async def list_services():
    """
    List all registered services with their versions.

    Returns deployment information for each team service.
    """
    services = []

    for team in route_router.get_available_teams():
        route = route_router.get_route(team)
        if route:
            # Fetch version from service
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{route.url}/health")
                    data = response.json()
                    version = data.get("version", "unknown")
            except Exception:
                version = "unreachable"

            services.append(ServiceInfo(
                name=f"{team}-api",
                namespace=team,
                url=route.url,
                version=version,
                deployed_at=None,  # Could fetch from K8s API
                image_tag=None     # Could fetch from deployment
            ))

    # Add gateway itself
    services.append(ServiceInfo(
        name="gateway",
        namespace="platform",
        url="http://gateway.platform.svc.cluster.local",
        version=os.getenv("SERVICE_VERSION", "unknown")
    ))

    return services


@router.get("/health", response_model=List[HealthStatus])
async def get_health():
    """
    Get aggregated health status for all teams.

    Checks readiness endpoint of each team service.
    """
    health_statuses = []

    teams = ["quant", "finetune", "eval"]

    async def check_team_health(team: str) -> HealthStatus:
        route = route_router.get_route(team)
        if not route:
            return HealthStatus(
                team=team,
                status="unknown",
                ready_pods=0,
                total_pods=0,
                last_check=datetime.utcnow().isoformat()
            )

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{route.url}/ready")
                if response.status_code == 200:
                    status = "healthy"
                elif response.status_code == 503:
                    status = "degraded"
                else:
                    status = "unhealthy"
        except Exception:
            status = "unhealthy"

        return HealthStatus(
            team=team,
            status=status,
            ready_pods=1 if status == "healthy" else 0,  # Simplified
            total_pods=1,
            last_check=datetime.utcnow().isoformat()
        )

    # Check all teams in parallel
    results = await asyncio.gather(*[check_team_health(t) for t in teams])
    health_statuses.extend(results)

    return health_statuses


@router.get("/stats", response_model=PlatformStats)
async def get_stats():
    """
    Get platform-wide statistics for the last 24 hours.

    Aggregates metrics from Prometheus.
    """
    # In production, query Prometheus API
    # For now, return mock data structure

    now = datetime.utcnow()
    window_start = now - timedelta(hours=24)

    return PlatformStats(
        total_requests_24h=1234567,
        error_rate_percent=0.12,
        p50_latency_ms=45.3,
        p95_latency_ms=234.5,
        p99_latency_ms=567.8,
        requests_by_team={
            "quant": 500000,
            "finetune": 450000,
            "eval": 284567
        },
        errors_by_team={
            "quant": 234,
            "finetune": 567,
            "eval": 123
        },
        window_start=window_start.isoformat(),
        window_end=now.isoformat()
    )


@router.post("/test", response_model=TestResponse)
async def run_test(request: TestRequest):
    """
    Execute a test prediction for a specific team.

    Returns the correlation ID and result for tracing.
    """
    import uuid
    import time

    correlation_id = f"test-{uuid.uuid4().hex[:8]}"
    start_time = time.time()

    route = route_router.get_route(request.team)
    if not route:
        return TestResponse(
            correlation_id=correlation_id,
            team=request.team,
            status="error",
            latency_ms=0,
            error=f"Unknown team: {request.team}"
        )

    try:
        async with httpx.AsyncClient(timeout=route.timeout_ms / 1000) as client:
            response = await client.post(
                f"{route.url}/predict",
                json={
                    "prompt": request.prompt,
                    "max_tokens": request.max_tokens
                },
                headers={"X-Correlation-ID": correlation_id}
            )

            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                return TestResponse(
                    correlation_id=correlation_id,
                    team=request.team,
                    status="success",
                    latency_ms=latency_ms,
                    response=response.json()
                )
            else:
                return TestResponse(
                    correlation_id=correlation_id,
                    team=request.team,
                    status="error",
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}: {response.text}"
                )

    except httpx.TimeoutException:
        return TestResponse(
            correlation_id=correlation_id,
            team=request.team,
            status="timeout",
            latency_ms=(time.time() - start_time) * 1000,
            error=f"Request timed out after {route.timeout_ms}ms"
        )
    except Exception as e:
        return TestResponse(
            correlation_id=correlation_id,
            team=request.team,
            status="error",
            latency_ms=(time.time() - start_time) * 1000,
            error=str(e)
        )


# Register router in gateway main.py
# from ops_api import router as ops_router
# app.include_router(ops_router)
