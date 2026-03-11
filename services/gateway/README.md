# services/gateway/

API Gateway service — the single entry point for all client requests. Routes prediction requests to team-specific services with A/B testing support, correlation ID tracking, and OpenTelemetry tracing.

## Architecture

```mermaid
graph TD
    Client[Client, Grafana Plugin] -->|POST /api/team/predict| GW[Gateway :8000]
    Client -->|GET /ops/*| GW

    GW -->|Router.get_route| RC[RouteConfig]
    RC -->|A/B variant selection| GW

    GW -->|httpx forward| QA[quant-api :8000]
    GW -->|httpx forward| FA[finetune-api :8000]
    GW -->|httpx forward| EA[eval-api :8000]

    GW -->|W3C Trace Context| OTEL[OTEL Collector]

    subgraph "Ops API"
        SVC[/services]
        HEALTH[/health]
        STATS[/stats]
        TEST[/test]
    end
    GW --> SVC
    GW --> HEALTH
    GW --> STATS
    GW --> TEST
```

## Files

| File               | Purpose                                                                              |
| ------------------ | ------------------------------------------------------------------------------------ |
| `main.py`          | FastAPI app, health probes, prediction routing endpoint                              |
| `routes.py`        | Alternative router module with `/api/{team}/predict` endpoint                        |
| `routing.py`       | `Router` class — parses route table JSON, A/B variant selection                      |
| `spans.py`         | OpenTelemetry span attribute helpers for route and backend tracing                   |
| `propagation.py`   | W3C Trace Context + Baggage header injection for outbound calls                      |
| `ops_api.py`       | Operations API endpoints (`/ops/services`, `/ops/health`, `/ops/stats`, `/ops/test`) |
| `Dockerfile`       | Container build (Python 3.11-slim, includes shared/ library)                         |
| `requirements.txt` | Python dependencies (FastAPI, httpx, OpenTelemetry, boto3)                           |

## Key Components

### Router (routing.py)

Manages team-to-URL routing with optional weighted A/B testing:

```python
class Router:
    """Routes requests to team services with A/B support."""

    def get_route(self, team: str) -> Optional[RouteConfig]:
        """Get route configuration for a team."""
        return self.routes.get(team)

    def select_variant(self, team: str) -> Optional[str]:
        """Select A/B variant based on configured weights."""
        # Weighted random selection from ab_variants config
```

### Span Attributes (spans.py)

Sets `lab.route.*`, `lab.ab.*`, and `lab.backend.*` attributes per design-08-otel-schema:

```python
def set_route_attributes(span, team, decision, reason, policy_id, ab_bucket=None):
    span.set_attribute("lab.route.target.team", team)
    span.set_attribute("lab.route.decision", decision)
    span.set_attribute("lab.ab.enabled", ab_bucket is not None)
```

### Ops API (ops_api.py)

Exposes operational endpoints consumed by the Grafana plugin. Queries Prometheus for real-time metrics:

```python
@router.get("/ops/services")   # List registered services with versions
@router.get("/ops/health")     # Health status per team
@router.get("/ops/stats")      # 24h request counts, error rates, latency percentiles
@router.post("/ops/test")      # Execute test prediction with tracing
```

## Configuration

The route table is provided via the `ROUTE_TABLE` environment variable (JSON):

```json
{
  "quant": { "url": "http://quant-api.quant.svc:8000", "timeout_ms": 30000 },
  "finetune": {
    "url": "http://finetune-api.finetune.svc:8000",
    "timeout_ms": 60000
  },
  "eval": { "url": "http://eval-api.eval.svc:8000", "timeout_ms": 45000 }
}
```

## Response Headers

Every prediction response includes tracking headers:

- `X-Correlation-ID` — Request correlation ID (generated if not provided)
- `X-Route-Team` — Team that handled the request
- `X-Route-Variant` — A/B variant selected
- `X-Latency-Ms` — End-to-end latency in milliseconds
