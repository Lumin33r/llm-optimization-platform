# LLM Platform Operations Panel

Grafana panel plugin for the LLM Optimization Platform operations dashboard.

## Overview

This plugin provides a unified operations view within Grafana, displaying:

- **Health Overview** — Real-time health status per team (quant, finetune, eval)
- **Platform Stats** — 24h request counts, error rates, and latency percentiles
- **Services Table** — All registered services with versions and deployment info
- **Test Console** — Execute test predictions and trace via correlation ID

## Architecture

The plugin communicates with the Gateway ops API (`/ops/*` endpoints) to fetch live platform data. It polls at a configurable interval (default: 30s).

```
Grafana Panel  →  Gateway /ops/services
                  Gateway /ops/health
                  Gateway /ops/stats
                  Gateway /ops/test (POST)
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

| Option           | Description                      | Default                                     |
| ---------------- | -------------------------------- | ------------------------------------------- |
| Gateway URL      | Base URL for the Gateway ops API | `http://gateway.platform.svc.cluster.local` |
| Refresh Interval | Polling interval in seconds      | `30`                                        |

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
    │   ├── OpsPanel.tsx       # Main panel component
    │   ├── ServicesTable.tsx   # Services table
    │   ├── HealthOverview.tsx  # Health indicators
    │   ├── StatsCards.tsx      # Stats summary cards
    │   └── TestConsole.tsx     # Test prediction console
    └── styles/
        └── panel.css          # Base CSS styles
```
