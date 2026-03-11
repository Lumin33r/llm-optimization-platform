# k8s/scripts/

Shell helpers for Kubernetes deployment operations. Wraps `kubectl` commands with environment-aware paths and validation.

## Files

| Script        | Purpose                                                         |
| ------------- | --------------------------------------------------------------- |
| `apply.sh`    | Applies Kustomize overlay — namespaces first, then full overlay |
| `diff.sh`     | Previews rendered manifests and diffs against live cluster      |
| `rollback.sh` | Rolls back a deployment to a previous (or specific) revision    |

## Usage

```bash
# Apply dev environment
k8s/scripts/apply.sh dev

# Preview changes before applying
k8s/scripts/diff.sh dev

# Rollback gateway to previous revision
k8s/scripts/rollback.sh gateway platform

# Rollback to specific revision
k8s/scripts/rollback.sh quant-api quant 2
```

## apply.sh Flow

1. Apply namespaces first (ensures they exist before other resources)
2. Preview diff against live cluster
3. Apply full Kustomize overlay
4. Print deployment and pod status
