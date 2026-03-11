# prometheus/

Prometheus recording rules that pre-compute frequently queried metrics for dashboard efficiency.

## Files

| File                   | Purpose                         |
| ---------------------- | ------------------------------- |
| `recording-rules.yaml` | Pre-computed PromQL expressions |

## Recording Rules

```yaml
groups:
  - name: llm_platform_recording_rules
    interval: 30s
    rules:
      # Per-service request rate (5m window)
      - record: service:http_requests:rate5m

      # Per-service error rate ratio
      - record: service:http_error_rate:ratio5m

      # Per-service P95 latency
      - record: service:http_latency_p95:seconds

      # SageMaker invoke P95 latency by endpoint
      - record: sagemaker:invoke_latency_p95:seconds

      # Gateway requests by team
      - record: gateway:requests_by_team:rate5m

      # Pod restart detection
      - record: k8s:pod_restarts:increase5m
```

## Relationship to Other Components

- **k8s/base/observability/prometheus-config.yaml** loads these rules
- **scripts/generate_dashboard.py** uses these pre-computed metrics
- **grafana-plugins/** dashboards query these recording rules for efficiency
