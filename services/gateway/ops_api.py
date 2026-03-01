"""Operations API for the LLM Platform dashboard."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import httpx
import asyncio
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["operations"])

# --------------- Prometheus helper ---------------
PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://prometheus.observability.svc.cluster.local:9090"
)


async def _prom_query(query: str) -> list:
    """Execute an instant PromQL query and return the result list."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
            )
            data = resp.json()
            if data.get("status") == "success":
                return data["data"]["result"]
            logger.warning("Prometheus query failed: %s — %s", query, data)
            return []
    except Exception as exc:
        logger.warning("Prometheus unreachable for query %s: %s", query, exc)
        return []


def _scalar(results: list, default: float = 0.0) -> float:
    """Extract a single scalar value from a Prometheus instant-query result."""
    if results and results[0].get("value"):
        raw = results[0]["value"][1]  # [timestamp, "value_string"]
        val = float(raw)
        # NaN / Inf → default
        if val != val or val == float("inf") or val == float("-inf"):
            return default
        return val
    return default


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


# Service registry — lazy import to avoid circular dependency
# main.py creates the Router instance; we access it at request time
def _get_router():
    from main import router
    return router


@router.get("/services", response_model=List[ServiceInfo])
async def list_services():
    """
    List all registered services with their versions.

    Returns deployment information for each team service.
    """
    services = []

    route_router = _get_router()
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

    route_router = _get_router()

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

    Queries Prometheus HTTP API for live metrics.
    """
    now = datetime.utcnow()
    window_start = now - timedelta(hours=24)

    # --- Fire all PromQL queries in parallel ---
    (
        total_res,
        err_rate_res,
        p50_res,
        p95_res,
        p99_res,
        req_by_team_res,
        err_by_team_res,
    ) = await asyncio.gather(
        _prom_query('sum(increase(gateway_requests_total[24h]))'),
        _prom_query(
            'sum(increase(gateway_requests_total{status!="success"}[24h]))'
            ' / sum(increase(gateway_requests_total[24h])) * 100'
        ),
        _prom_query(
            'histogram_quantile(0.50, sum(rate(gateway_latency_ms_bucket[24h])) by (le))'
        ),
        _prom_query(
            'histogram_quantile(0.95, sum(rate(gateway_latency_ms_bucket[24h])) by (le))'
        ),
        _prom_query(
            'histogram_quantile(0.99, sum(rate(gateway_latency_ms_bucket[24h])) by (le))'
        ),
        _prom_query('sum by (team) (increase(gateway_requests_total[24h]))'),
        _prom_query(
            'sum by (team) (increase(gateway_requests_total{status!="success"}[24h]))'
        ),
    )

    # --- Parse scalar results ---
    total_requests = int(_scalar(total_res))
    error_rate = round(_scalar(err_rate_res), 2)
    p50 = round(_scalar(p50_res), 1)
    p95 = round(_scalar(p95_res), 1)
    p99 = round(_scalar(p99_res), 1)

    # --- Parse per-team vector results ---
    requests_by_team: Dict[str, int] = {}
    for item in req_by_team_res:
        team = item["metric"].get("team", "unknown")
        requests_by_team[team] = int(float(item["value"][1]))

    errors_by_team: Dict[str, int] = {}
    for item in err_by_team_res:
        team = item["metric"].get("team", "unknown")
        errors_by_team[team] = int(float(item["value"][1]))

    return PlatformStats(
        total_requests_24h=total_requests,
        error_rate_percent=error_rate,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        requests_by_team=requests_by_team,
        errors_by_team=errors_by_team,
        window_start=window_start.isoformat(),
        window_end=now.isoformat(),
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

    route_router = _get_router()
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


# --------------- Data Engine proxy ---------------
DATA_ENGINE_URL = os.getenv(
    "DATA_ENGINE_URL",
    "http://data-engine.platform.svc.cluster.local:8000"
)


@router.get("/promptsets")
async def list_promptsets():
    """List available promptsets (proxied from data-engine)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{DATA_ENGINE_URL}/promptsets")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Failed to list promptsets: {e}")
        raise HTTPException(502, f"Data engine unavailable: {e}")


@router.get("/promptsets/{name}")
async def get_promptset(name: str):
    """Get promptset details (proxied from data-engine)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{DATA_ENGINE_URL}/promptsets/{name}")
            if resp.status_code == 404:
                raise HTTPException(404, f"Promptset '{name}' not found")
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get promptset: {e}")
        raise HTTPException(502, f"Data engine unavailable: {e}")


class HarnessRunRequest(BaseModel):
    promptset: str
    team: str
    variant: Optional[str] = None
    concurrency: int = 5
    max_prompts: Optional[int] = None


@router.post("/harness/run")
async def start_harness_run(req: HarnessRunRequest):
    """Start a harness run (proxied to data-engine)."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{DATA_ENGINE_URL}/harness/run",
                json=req.model_dump()
            )
            if resp.status_code == 404:
                raise HTTPException(404, resp.json().get("detail", "Not found"))
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start harness run: {e}")
        raise HTTPException(502, f"Data engine unavailable: {e}")


@router.get("/harness/runs")
async def list_harness_runs():
    """List harness runs (proxied from data-engine)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{DATA_ENGINE_URL}/harness/runs")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Failed to list harness runs: {e}")
        raise HTTPException(502, f"Data engine unavailable: {e}")


@router.get("/harness/runs/{run_id}")
async def get_harness_run(run_id: str):
    """Get harness run status/results (proxied from data-engine)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{DATA_ENGINE_URL}/harness/runs/{run_id}")
            if resp.status_code == 404:
                raise HTTPException(404, f"Run '{run_id}' not found")
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get harness run: {e}")
        raise HTTPException(502, f"Data engine unavailable: {e}")


# Register router in gateway main.py
# from ops_api import router as ops_router
# app.include_router(ops_router)
