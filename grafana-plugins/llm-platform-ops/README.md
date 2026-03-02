# LLM Platform Operations Panel

Grafana panel plugin for the LLM Optimization Platform operations dashboard.

## Overview

This plugin provides a unified operations view within Grafana, displaying:

- **Health Overview** — Real-time health status per team (quant, finetune, eval)
- **Platform Stats** — 24h request counts, error rates, and latency percentiles
- **Services Table** — All registered services with versions and deployment info
- **Test Console** — Execute test predictions and trace via correlation ID
- **Harness Console** — Run test harness batches and full benchmark suites (700 prompts)

## Architecture

The plugin communicates with the Gateway ops API (`/ops/*` endpoints) and data-engine
harness/benchmark endpoints via a **relative URL** (`/gateway-proxy`). An nginx reverse
proxy sidecar in the Grafana pod proxies `/gateway-proxy/` to the gateway's internal
K8s DNS name, so the plugin works from any browser without needing an external hostname.

```
Grafana Panel  →  /gateway-proxy/ops/services
                  /gateway-proxy/ops/health
                  /gateway-proxy/ops/stats
                  /gateway-proxy/ops/test         (POST)
                  /gateway-proxy/harness/benchmark (POST)
                  /gateway-proxy/harness/benchmark/{id} (GET)
```

## Prerequisites

- Grafana >= 9.0.0 (deployed via [design-03-observability.md](../../docs/design-03-observability.md))
- Gateway with ops API endpoints (see [design-04-sagemaker.md](../../docs/design-04-sagemaker.md))

## Build

```bash
cd grafana-plugins/llm-platform-ops

# Install dependencies
npm install

# Development build (watch mode)
npm run dev

# Production build
npm run build

# Package as zip
npm run package
# Output: llmplatform-ops-panel-1.0.0.zip
```

## Install in Grafana

### Option 1: kubectl cp

```bash
kubectl cp dist/ grafana-pod:/var/lib/grafana/plugins/llmplatform-ops-plugin/ -n observability
kubectl rollout restart deployment/grafana -n observability
```

### Option 2: Volume mount

Mount the plugin directory into the Grafana pod via a volume in the Grafana deployment spec.

## Panel Configuration

After install, add a new panel in Grafana and select **LLM Platform Ops**.

| Option           | Description                      | Default                                      |
| ---------------- | -------------------------------- | -------------------------------------------- |
| Gateway URL      | Base URL for the Gateway ops API | `/gateway-proxy` (proxied via nginx sidecar) |
| Refresh Interval | Polling interval in seconds      | `30`                                         |

## File Structure

```
llm-platform-ops/
├── package.json
├── tsconfig.json
├── webpack.config.js
├── plugin.json
├── README.md
└── src/
    ├── module.ts              # Plugin entry point
    ├── plugin.json            # Runtime config
    ├── types.ts               # TypeScript interfaces
    ├── api/
    │   └── opsApi.ts          # Gateway ops API client
    ├── components/
    │   ├── OpsPanel.tsx        # Main panel component
    │   ├── ServicesTable.tsx    # Services table
    │   ├── HealthOverview.tsx   # Health indicators
    │   ├── StatsCards.tsx       # Stats summary cards
    │   ├── TestConsole.tsx      # Test prediction console
    │   └── HarnessConsole.tsx   # Test harness & benchmark runner
    └── styles/
        └── panel.css          # Base CSS styles
```
