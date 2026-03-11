# k8s/quant/

Controlled failure scenario manifests for observability validation and failure mode testing. Used by `scripts/failure-demos.sh` to verify the platform handles failures gracefully.

## Scenarios

| File                            | Failure Type                                     |
| ------------------------------- | ------------------------------------------------ |
| `deployment-slow-startup.yaml`  | Readiness-gated traffic — tests slow pod startup |
| `deployment-exceeds-quota.yaml` | Resource quota rejection — pods stuck in Pending |
| `resourcequota-tight.yaml`      | Tight quota that causes rejection                |

## Usage

```bash
# Run all failure demos
bash scripts/failure-demos.sh

# Manual: test quota rejection
kubectl apply -f k8s/quant/resourcequota-tight.yaml
kubectl apply -f k8s/quant/deployment-exceeds-quota.yaml  # Expected: fails
```

## Observability Verification

Each scenario is designed to be visible in Grafana dashboards:

- **Slow startup**: Traffic drops to ready pods only, no 5xx errors
- **Quota rejection**: Pods show as Pending, no traffic shift
- **Timeout**: 504 responses from FastAPI, SageMaker latency remains normal
