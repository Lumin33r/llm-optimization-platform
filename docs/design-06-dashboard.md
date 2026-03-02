# Design Document 6: Internal Operations UI / Grafana Plugin

## Overview

This document defines the operations dashboard for the LLM Optimization Platform. The dashboard is implemented as a **Grafana Panel Plugin** (React), not a standalone application.

**Key Design Decisions**:

- Plugin integrates directly into Grafana for unified observability
- Gateway exposes ops API endpoints for service management
- Real-time updates via polling (configurable interval)
- "Monday Morning" view for quick platform health assessment
- Baseline model status visible alongside team services (see [design-10-models.md](design-10-models.md))

---

## Quick Start (Implementation Order)

```bash
# 1. Prerequisites (after design-03 Grafana deployed)
cd services/grafana-plugin/llmplatform-ops-plugin

# 2. Install dependencies and build
npm install && npm run build

# 3. Copy plugin to Grafana
kubectl cp dist/ grafana-pod:/var/lib/grafana/plugins/llmplatform-ops-plugin/ -n observability

# 4. Restart Grafana to load plugin
kubectl rollout restart deployment/grafana -n observability

# 5. Create dashboard with plugin panel
# In Grafana UI: Add panel → Select "LLM Platform Ops"
```

**Depends On**: [design-03-observability.md](design-03-observability.md) (Grafana), [design-04-sagemaker.md](design-04-sagemaker.md) (ops API)
**Feeds Into**: No downstream dependencies

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                        Grafana                                                    │
│                                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐│
│  │                           LLM Platform Operations Dashboard                                  ││
│  │                                                                                              ││
│  │  ┌───────────────────────────────────────────────────────────────────────────────────────┐ ││
│  │  │                     LLM Platform Ops Plugin (React Panel)                             │ ││
│  │  │                                                                                        │ ││
│  │  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │ ││
│  │  │   │   Services   │  │    Health    │  │    Stats     │  │     Test     │             │ ││
│  │  │   │    Table     │  │   Overview   │  │   Summary    │  │   Console    │             │ ││
│  │  │   │              │  │              │  │              │  │              │             │ ││
│  │  │   │ • gateway    │  │   ● quant    │  │ Requests: 1M │  │ POST /predict│             │ ││
│  │  │   │ • quant-api  │  │   ● finetune │  │ Errors: 0.1% │  │              │             │ ││
│  │  │   │ • finetune-  │  │   ● eval     │  │ P95: 234ms   │  │ [Run Test]   │             │ ││
│  │  │   │   api        │  │              │  │              │  │              │             │ ││
│  │  │   │ • eval-api   │  │              │  │              │  │              │             │ ││
│  │  │   └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘             │ ││
│  │  │                                                                                        │ ││
│  │  └───────────────────────────────────────────────────────────────────────────────────────┘ ││
│  │                                                                                              ││
│  │  ┌──────────────────────────────┐  ┌──────────────────────────────┐                        ││
│  │  │  Prometheus Panel (Metrics)  │  │     Loki Panel (Logs)        │                        ││
│  │  │  - Request rate over time    │  │  - Recent errors             │                        ││
│  │  │  - Latency percentiles       │  │  - Team activity             │                        ││
│  │  └──────────────────────────────┘  └──────────────────────────────┘                        ││
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              │ HTTP
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   Gateway (platform namespace)                                    │
│                                                                                                   │
│   Ops API Endpoints:                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐  │
│   │  GET  /ops/services    → List registered services + versions                             │  │
│   │  GET  /ops/health      → Aggregated health status per team                               │  │
│   │  GET  /ops/stats       → Request counts, error rates, latencies (24h window)             │  │
│   │  POST /ops/test        → Trigger test prediction (returns correlation ID)                │  │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Gateway Ops API

### API Endpoints

| Endpoint        | Method | Description                      | Response                         |
| --------------- | ------ | -------------------------------- | -------------------------------- |
| `/ops/services` | GET    | List all registered services     | Array of service info            |
| `/ops/health`   | GET    | Aggregated health status         | Health status per team           |
| `/ops/stats`    | GET    | Platform statistics (24h window) | Request counts, error rates, P95 |
| `/ops/test`     | POST   | Execute test prediction          | Correlation ID, result           |

#### Data-Engine Harness & Benchmark Endpoints

| Endpoint                  | Method | Description                                     |
| ------------------------- | ------ | ----------------------------------------------- |
| `/ops/promptsets`         | GET    | List available promptsets                       |
| `/ops/harness/run`        | POST   | Execute single harness run                      |
| `/ops/harness/runs`       | GET    | List past harness runs                          |
| `/ops/harness/runs/{id}`  | GET    | Get specific harness run results                |
| `/harness/benchmark`      | POST   | Start full benchmark (all 3 teams, 700 prompts) |
| `/harness/benchmark/{id}` | GET    | Get benchmark status/results                    |

> **See also:** [design-12-benchmark.md](design-12-benchmark.md) for the full benchmark test battery specification.

### Implementation

```python
# services/gateway/ops_api.py
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
```

---

## Grafana Plugin Structure

### Plugin Directory Layout

```
grafana-plugins/
└── llm-platform-ops/
    ├── package.json
    ├── tsconfig.json
    ├── webpack.config.js
    ├── plugin.json              # Grafana plugin manifest
    ├── src/
    │   ├── module.ts            # Plugin entry point
    │   ├── plugin.json          # Runtime config
    │   ├── types.ts             # TypeScript interfaces
    │   ├── api/
    │   │   └── opsApi.ts        # Gateway ops API client
    │   ├── components/
    │   │   ├── OpsPanel.tsx       # Main panel component
    │   │   ├── ServicesTable.tsx
    │   │   ├── HealthOverview.tsx
    │   │   ├── StatsCards.tsx
    │   │   ├── TestConsole.tsx
    │   │   └── HarnessConsole.tsx # Test harness & benchmark runner
    │   └── styles/
    │       └── panel.css
    └── README.md
```

### Plugin Manifest

```json
// grafana-plugins/llm-platform-ops/src/plugin.json
{
  "type": "panel",
  "name": "LLM Platform Operations",
  "id": "llmplatform-ops-panel",
  "info": {
    "description": "Operations dashboard for LLM Optimization Platform",
    "author": {
      "name": "Platform Team"
    },
    "version": "1.0.0",
    "updated": "2024-01-01"
  },
  "dependencies": {
    "grafanaDependency": ">=9.0.0",
    "plugins": []
  }
}
```

### Main Panel Component

```typescript
// grafana-plugins/llm-platform-ops/src/components/OpsPanel.tsx
import React, { useState, useEffect } from 'react';
import { PanelProps } from '@grafana/data';
import { useStyles2 } from '@grafana/ui';
import { css } from '@emotion/css';
import { ServicesTable } from './ServicesTable';
import { HealthOverview } from './HealthOverview';
import { StatsCards } from './StatsCards';
import { TestConsole } from './TestConsole';
import { OpsApi, ServiceInfo, HealthStatus, PlatformStats } from '../api/opsApi';

interface OpsPanelOptions {
  gatewayUrl: string;
  refreshInterval: number;  // seconds
}

interface Props extends PanelProps<OpsPanelOptions> {}

export const OpsPanel: React.FC<Props> = ({ options, width, height }) => {
  const styles = useStyles2(getStyles);

  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [health, setHealth] = useState<HealthStatus[]>([]);
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const api = new OpsApi(options.gatewayUrl);

  // Fetch data on mount and at interval
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [servicesData, healthData, statsData] = await Promise.all([
          api.getServices(),
          api.getHealth(),
          api.getStats()
        ]);
        setServices(servicesData);
        setHealth(healthData);
        setStats(statsData);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();

    const interval = setInterval(fetchData, options.refreshInterval * 1000);
    return () => clearInterval(interval);
  }, [options.gatewayUrl, options.refreshInterval]);

  if (loading && !services.length) {
    return <div className={styles.loading}>Loading...</div>;
  }

  if (error) {
    return <div className={styles.error}>{error}</div>;
  }

  return (
    <div className={styles.container} style={{ width, height }}>
      <div className={styles.header}>
        <h2>LLM Platform Operations</h2>
        <span className={styles.timestamp}>
          Last updated: {new Date().toLocaleTimeString()}
        </span>
      </div>

      <div className={styles.grid}>
        <div className={styles.column}>
          <HealthOverview health={health} />
        </div>

        <div className={styles.column}>
          {stats && <StatsCards stats={stats} />}
        </div>

        <div className={styles.fullWidth}>
          <ServicesTable services={services} />
        </div>

        <div className={styles.fullWidth}>
          <TestConsole api={api} />
        </div>
      </div>
    </div>
  );
};

const getStyles = () => ({
  container: css`
    padding: 16px;
    overflow: auto;
  `,
  header: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  `,
  timestamp: css`
    color: #8e8e8e;
    font-size: 12px;
  `,
  grid: css`
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  `,
  column: css`
    background: #1e1e1e;
    border-radius: 4px;
    padding: 12px;
  `,
  fullWidth: css`
    grid-column: 1 / -1;
    background: #1e1e1e;
    border-radius: 4px;
    padding: 12px;
  `,
  loading: css`
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100%;
  `,
  error: css`
    color: #ff5555;
    padding: 16px;
  `
});
```

### API Client

```typescript
// grafana-plugins/llm-platform-ops/src/api/opsApi.ts

export interface ServiceInfo {
  name: string;
  namespace: string;
  url: string;
  version: string;
  deployed_at?: string;
  image_tag?: string;
}

export interface HealthStatus {
  team: string;
  status: "healthy" | "degraded" | "unhealthy" | "unknown";
  ready_pods: number;
  total_pods: number;
  last_check: string;
}

export interface PlatformStats {
  total_requests_24h: number;
  error_rate_percent: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  requests_by_team: Record<string, number>;
  errors_by_team: Record<string, number>;
  window_start: string;
  window_end: string;
}

export interface TestRequest {
  team: string;
  prompt?: string;
  max_tokens?: number;
}

export interface TestResponse {
  correlation_id: string;
  team: string;
  status: "success" | "error" | "timeout";
  latency_ms: number;
  response?: Record<string, unknown>;
  error?: string;
}

export class OpsApi {
  constructor(private baseUrl: string) {}

  async getServices(): Promise<ServiceInfo[]> {
    const response = await fetch(`${this.baseUrl}/ops/services`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getHealth(): Promise<HealthStatus[]> {
    const response = await fetch(`${this.baseUrl}/ops/health`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getStats(): Promise<PlatformStats> {
    const response = await fetch(`${this.baseUrl}/ops/stats`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async runTest(request: TestRequest): Promise<TestResponse> {
    const response = await fetch(`${this.baseUrl}/ops/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
}
```

### Services Table Component

```typescript
// grafana-plugins/llm-platform-ops/src/components/ServicesTable.tsx
import React from 'react';
import { css } from '@emotion/css';
import { ServiceInfo } from '../api/opsApi';

interface Props {
  services: ServiceInfo[];
}

export const ServicesTable: React.FC<Props> = ({ services }) => {
  const styles = getStyles();

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Registered Services</h3>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Service</th>
            <th>Namespace</th>
            <th>Version</th>
            <th>Image Tag</th>
          </tr>
        </thead>
        <tbody>
          {services.map(service => (
            <tr key={service.name}>
              <td>{service.name}</td>
              <td><span className={styles.namespace}>{service.namespace}</span></td>
              <td>{service.version}</td>
              <td>{service.image_tag || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const getStyles = () => ({
  container: css``,
  title: css`
    margin-bottom: 12px;
    font-size: 14px;
  `,
  table: css`
    width: 100%;
    border-collapse: collapse;

    th, td {
      text-align: left;
      padding: 8px 12px;
      border-bottom: 1px solid #333;
    }

    th {
      color: #8e8e8e;
      font-weight: 500;
    }
  `,
  namespace: css`
    background: #333;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
  `
});
```

### Health Overview Component

```typescript
// grafana-plugins/llm-platform-ops/src/components/HealthOverview.tsx
import React from 'react';
import { css } from '@emotion/css';
import { HealthStatus } from '../api/opsApi';

interface Props {
  health: HealthStatus[];
}

export const HealthOverview: React.FC<Props> = ({ health }) => {
  const styles = getStyles();

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return '#73bf69';
      case 'degraded': return '#ff9830';
      case 'unhealthy': return '#ff5555';
      default: return '#8e8e8e';
    }
  };

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Team Health</h3>
      <div className={styles.grid}>
        {health.map(h => (
          <div key={h.team} className={styles.card}>
            <div
              className={styles.indicator}
              style={{ backgroundColor: getStatusColor(h.status) }}
            />
            <div className={styles.info}>
              <span className={styles.team}>{h.team}</span>
              <span className={styles.status}>{h.status}</span>
              <span className={styles.pods}>
                {h.ready_pods}/{h.total_pods} pods
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const getStyles = () => ({
  container: css``,
  title: css`
    margin-bottom: 12px;
    font-size: 14px;
  `,
  grid: css`
    display: flex;
    flex-direction: column;
    gap: 8px;
  `,
  card: css`
    display: flex;
    align-items: center;
    padding: 8px 12px;
    background: #252525;
    border-radius: 4px;
  `,
  indicator: css`
    width: 12px;
    height: 12px;
    border-radius: 50%;
    margin-right: 12px;
  `,
  info: css`
    display: flex;
    flex-direction: column;
  `,
  team: css`
    font-weight: 500;
    text-transform: capitalize;
  `,
  status: css`
    font-size: 12px;
    color: #8e8e8e;
  `,
  pods: css`
    font-size: 11px;
    color: #666;
  `
});
```

### Test Console Component

```typescript
// grafana-plugins/llm-platform-ops/src/components/TestConsole.tsx
import React, { useState } from 'react';
import { css } from '@emotion/css';
import { OpsApi, TestResponse } from '../api/opsApi';

interface Props {
  api: OpsApi;
}

export const TestConsole: React.FC<Props> = ({ api }) => {
  const styles = getStyles();

  const [team, setTeam] = useState('quant');
  const [prompt, setPrompt] = useState('Test health check prompt');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TestResponse | null>(null);

  const runTest = async () => {
    setLoading(true);
    setResult(null);

    try {
      const response = await api.runTest({
        team,
        prompt,
        max_tokens: 10
      });
      setResult(response);
    } catch (err) {
      setResult({
        correlation_id: 'error',
        team,
        status: 'error',
        latency_ms: 0,
        error: err instanceof Error ? err.message : 'Unknown error'
      });
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success': return '#73bf69';
      case 'timeout': return '#ff9830';
      case 'error': return '#ff5555';
      default: return '#8e8e8e';
    }
  };

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Test Console</h3>

      <div className={styles.form}>
        <div className={styles.field}>
          <label>Team</label>
          <select value={team} onChange={e => setTeam(e.target.value)}>
            <option value="quant">Quantization</option>
            <option value="finetune">Fine-tuning</option>
            <option value="eval">Evaluation</option>
          </select>
        </div>

        <div className={styles.field}>
          <label>Prompt</label>
          <input
            type="text"
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="Test prompt..."
          />
        </div>

        <button
          className={styles.button}
          onClick={runTest}
          disabled={loading}
        >
          {loading ? 'Running...' : 'Run Test'}
        </button>
      </div>

      {result && (
        <div className={styles.result}>
          <div className={styles.resultHeader}>
            <span
              className={styles.statusBadge}
              style={{ backgroundColor: getStatusColor(result.status) }}
            >
              {result.status}
            </span>
            <span className={styles.latency}>{result.latency_ms.toFixed(0)}ms</span>
          </div>
          <div className={styles.correlationId}>
            Correlation ID: <code>{result.correlation_id}</code>
          </div>
          {result.error && (
            <div className={styles.errorMessage}>{result.error}</div>
          )}
          {result.response && (
            <pre className={styles.responseJson}>
              {JSON.stringify(result.response, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
};

const getStyles = () => ({
  container: css``,
  title: css`
    margin-bottom: 12px;
    font-size: 14px;
  `,
  form: css`
    display: flex;
    gap: 12px;
    align-items: flex-end;
    margin-bottom: 16px;
  `,
  field: css`
    display: flex;
    flex-direction: column;
    gap: 4px;

    label {
      font-size: 12px;
      color: #8e8e8e;
    }

    select, input {
      padding: 8px 12px;
      background: #333;
      border: 1px solid #444;
      border-radius: 4px;
      color: #fff;
    }

    input {
      width: 300px;
    }
  `,
  button: css`
    padding: 8px 16px;
    background: #3871dc;
    border: none;
    border-radius: 4px;
    color: #fff;
    cursor: pointer;

    &:hover {
      background: #4c85ed;
    }

    &:disabled {
      background: #444;
      cursor: not-allowed;
    }
  `,
  result: css`
    background: #252525;
    padding: 12px;
    border-radius: 4px;
  `,
  resultHeader: css`
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
  `,
  statusBadge: css`
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    text-transform: uppercase;
  `,
  latency: css`
    color: #8e8e8e;
    font-size: 14px;
  `,
  correlationId: css`
    font-size: 12px;
    color: #8e8e8e;
    margin-bottom: 8px;

    code {
      background: #333;
      padding: 2px 6px;
      border-radius: 2px;
    }
  `,
  errorMessage: css`
    color: #ff5555;
    font-size: 13px;
    margin-top: 8px;
  `,
  responseJson: css`
    background: #1a1a1a;
    padding: 12px;
    border-radius: 4px;
    font-size: 12px;
    overflow: auto;
    max-height: 150px;
  `
});
```

---

## Monday Morning Panel Layout

The "Monday Morning" view provides quick platform health assessment:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              Monday Morning Platform Status                                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  Total Requests │  │   Error Rate    │  │   P95 Latency   │  │   All Services  │             │
│  │                 │  │                 │  │                 │  │                 │             │
│  │    1,234,567    │  │     0.12%       │  │     234 ms      │  │    4/4 UP ●     │             │
│  │    ▲ 12% 24h    │  │    ▼ 0.05%     │  │    ▲ 15ms       │  │                 │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                                                   │
│  ┌──────────────────────────────────────────┬───────────────────────────────────────────────────┐│
│  │           Health by Team                 │           Request Distribution                    ││
│  │                                          │                                                   ││
│  │   ● quant     healthy  500K reqs        │         [==========] quant     40%              ││
│  │   ● finetune  healthy  450K reqs        │         [=========]  finetune  36%              ││
│  │   ● eval      healthy  284K reqs        │         [=======]    eval      24%              ││
│  │                                          │                                                   ││
│  └──────────────────────────────────────────┴───────────────────────────────────────────────────┘│
│                                                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐│
│  │                              Services & Versions                                             ││
│  │                                                                                              ││
│  │  Service        Namespace    Version     Image                    Deployed                  ││
│  │  ─────────────────────────────────────────────────────────────────────────────────────────  ││
│  │  gateway        platform     v1.2.0      sha-abc123               2h ago                    ││
│  │  quant-api      quant        v1.1.5      sha-def456               4h ago                    ││
│  │  finetune-api   finetune     v1.3.0      sha-ghi789               1d ago                    ││
│  │  eval-api       eval         v1.0.2      sha-jkl012               2d ago                    ││
│  │                                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐│
│  │                               Quick Test                                                     ││
│  │                                                                                              ││
│  │  Team: [quant ▾]  Prompt: [Health check...                    ]  [▶ Run Test]               ││
│  │                                                                                              ││
│  │  Result: ● success  234ms  correlation_id: test-a1b2c3d4                                    ││
│  │                                                                                              ││
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Grafana Dashboard Configuration (JSON)

```json
{
  "title": "LLM Platform Operations",
  "uid": "llm-platform-ops",
  "tags": ["llm", "platform", "ops"],
  "refresh": "30s",
  "panels": [
    {
      "id": 1,
      "title": "Platform Operations",
      "type": "llmplatform-ops-panel",
      "gridPos": { "x": 0, "y": 0, "w": 24, "h": 12 },
      "options": {
        "gatewayUrl": "/gateway-proxy",
        "refreshInterval": 30
      }
    },
    {
      "id": 2,
      "title": "Request Rate",
      "type": "timeseries",
      "gridPos": { "x": 0, "y": 12, "w": 12, "h": 8 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(gateway_requests_total[5m])) by (team)",
          "legendFormat": "{{team}}"
        }
      ]
    },
    {
      "id": 3,
      "title": "Error Rate",
      "type": "timeseries",
      "gridPos": { "x": 12, "y": 12, "w": 12, "h": 8 },
      "datasource": "Prometheus",
      "targets": [
        {
          "expr": "sum(rate(gateway_requests_total{status=~\"5..\"}[5m])) by (team) / sum(rate(gateway_requests_total[5m])) by (team)",
          "legendFormat": "{{team}}"
        }
      ]
    },
    {
      "id": 4,
      "title": "Recent Logs",
      "type": "logs",
      "gridPos": { "x": 0, "y": 20, "w": 24, "h": 6 },
      "datasource": "Loki",
      "targets": [
        {
          "expr": "{namespace=~\"platform|quant|finetune|eval\"} |= \"error\" or |= \"warn\"",
          "maxLines": 100
        }
      ]
    }
  ]
}
```

---

## Gateway Connectivity: Nginx Reverse Proxy

The Grafana plugin makes **client-side `fetch()` calls** from the user's browser. Browsers cannot resolve Kubernetes internal DNS names (`gateway.platform.svc.cluster.local`), so a reverse proxy sidecar is used.

### Architecture

The Grafana pod runs two containers:

| Container     | Port | Purpose                              |
| ------------- | ---- | ------------------------------------ |
| `nginx-proxy` | 3000 | User-facing reverse proxy            |
| `grafana`     | 3001 | Grafana server (internal to the pod) |

```
Browser :3000 → nginx → /             → Grafana :3001
                      → /gateway-proxy/ → gateway.platform.svc:8000
```

- The plugin's `gatewayUrl` option defaults to `/gateway-proxy` (a relative URL).
- nginx proxies `/gateway-proxy/` to the gateway's **internal K8s DNS** — no external ELB hostname required.
- WebSocket support is enabled for Grafana Live (`Upgrade` / `Connection: upgrade` headers).

> **Key Benefit:** The gateway URL never changes, even if the LoadBalancer is recreated. No `sed` patching needed in CI/CD.

See [design-03-observability.md](design-03-observability.md) for the full deployment YAML.

---

## Plugin Installation

### Build and Package

```bash
# Navigate to plugin directory
cd grafana-plugins/llm-platform-ops

# Install dependencies
npm install

# Build plugin
npm run build

# Create package
npm run package
# Output: llmplatform-ops-panel-1.0.0.zip
```

### Install in Grafana

```yaml
# K8s ConfigMap for plugin provisioning
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-plugin-config
  namespace: observability
data:
  plugins: |
    llmplatform-ops-panel=https://artifacts.example.com/grafana-plugins/llmplatform-ops-panel-1.0.0.zip
```

Or mount plugin directory directly:

```yaml
volumes:
  - name: plugins
    configMap:
      name: grafana-plugins
```

---

## Implementation Checklist

- [x] Implement Gateway ops API endpoints
  - [x] `GET /ops/services`
  - [x] `GET /ops/health`
  - [x] `GET /ops/stats`
  - [x] `POST /ops/test`
- [x] Create Grafana plugin project structure
- [x] Implement OpsApi client in TypeScript
- [x] Create OpsPanel main component
- [x] Implement sub-components:
  - [x] ServicesTable
  - [x] HealthOverview
  - [x] StatsCards
  - [x] TestConsole
  - [x] HarnessConsole (test harness + benchmark runner)
- [x] Build and package plugin
- [x] Deploy plugin to Grafana (custom Docker image)
- [x] Configure dashboard with plugin panel
- [x] Add Prometheus and Loki panels (26 panels via design-11)
- [x] Test live polling functionality
- [x] Test quick test functionality
- [x] Document panel configuration options
- [x] Nginx reverse proxy sidecar for gateway connectivity
- [x] Benchmark test battery (700 prompts, 3 teams) — see design-12
