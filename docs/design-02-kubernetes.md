# Design Document 2: Kubernetes Orchestration

## Overview

This document defines the Kubernetes orchestration layer for the LLM Optimization Platform. The design emphasizes:

- **6 Namespace Separation** - `platform`, `quant`, `finetune`, `eval`, `observability`, `llm-baseline`
- **Kustomize Structure** - Base + overlays for environment-specific configuration
- **Full Probe Coverage** - Startup, liveness, readiness probes for every deployment
- **Resource Controls** - ResourceQuotas and LimitRanges per namespace
- **IRSA Integration** - ServiceAccounts annotated with IAM role ARNs

---

## Quick Start (Implementation Order)

```bash
# 1. Prerequisites (after design-01 Terraform apply)
aws eks update-kubeconfig --name llmplatform-dev

# 2. Apply namespaces first
kubectl apply -k k8s/base/ --selector='kind=Namespace'

# 3. Apply full base configuration
kubectl apply -k k8s/base/

# 4. Apply environment overlay
kubectl apply -k k8s/overlays/dev/

# 5. Verify all deployments
kubectl get deployments -A -l app.kubernetes.io/part-of=llm-optimization-platform
```

**Depends On**: [design-01-infrastructure.md](design-01-infrastructure.md) (Terraform outputs)
**Feeds Into**: [design-03-observability.md](design-03-observability.md), [design-10-models.md](design-10-models.md)

---

## Architecture Diagram

```
                            ┌─────────────────────────────────────────────────────────────────┐
                            │                        EKS Cluster                               │
                            │                                                                  │
┌───────────────────────────┼──────────────────────────────────────────────────────────────────┤
│                           │                                                                  │
│   External Traffic        │                ┌───────────────────────┐                        │
│   ──────────────────────> │                │ ALB Ingress Controller │                        │
│                           │                │      (platform)        │                        │
│                           │                └───────────┬───────────┘                        │
│                           │                            │                                    │
│                           │        ┌───────────────────┴───────────────────┐               │
│                           │        │                                       │               │
│                           │        ▼                                       ▼               │
│                           │  ┌──────────────┐                       ┌──────────────┐       │
│                           │  │   Gateway    │                       │   Grafana    │       │
│                           │  │  (platform)  │                       │(observability)│       │
│                           │  └──────┬───────┘                       └──────────────┘       │
│                           │         │                                                      │
│                           │         │ ClusterIP Services                                   │
│                           │         ├──────────────┬──────────────┬───────────────┐       │
│                           │         ▼              ▼              ▼               │       │
│                           │   ┌──────────┐  ┌──────────┐   ┌──────────┐          │       │
│                           │   │quant-api │  │finetune- │   │eval-api  │          │       │
│                           │   │ (quant)  │  │api       │   │  (eval)  │          │       │
│                           │   │          │  │(finetune)│   │          │          │       │
│                           │   └──────────┘  └──────────┘   └──────────┘          │       │
│                           │                                                       │       │
│                           │         ┌────────────────────────────────────────────┐│       │
│                           │         │           observability namespace          ││       │
│                           │         │  ┌─────────┐ ┌──────┐ ┌──────┐ ┌────────┐ ││       │
│                           │         │  │Prometheus│ │Loki  │ │Tempo │ │  OTEL  │ ││       │
│                           │         │  │ /Mimir  │ │      │ │      │ │Collector│ ││       │
│                           │         │  └─────────┘ └──────┘ └──────┘ └────────┘ ││       │
│                           │         └────────────────────────────────────────────┘│       │
└───────────────────────────┴──────────────────────────────────────────────────────────────────┘
```

---

## Namespace Architecture

| Namespace       | Purpose                      | Key Workloads                    |
| --------------- | ---------------------------- | -------------------------------- |
| `platform`      | Core infrastructure services | Gateway, OTEL Collector sidecar  |
| `quant`         | Quantization team workloads  | quant-api deployment             |
| `finetune`      | Fine-tuning team workloads   | finetune-api deployment          |
| `eval`          | Evaluation team workloads    | eval-api deployment              |
| `observability` | Monitoring stack             | Grafana, Prometheus, Loki, Tempo |
| `llm-baseline`  | Baseline model inference     | vLLM deployment (Mistral-7B)     |

> **Note**: The `llm-baseline` namespace hosts 4 vLLM model variants on dedicated SPOT GPU nodes. Each team has its own model endpoint (AWQ, LoRA, Judge) with pod anti-affinity ensuring one model per node. See [design-10-models.md](design-10-models.md) for details.

---

## Directory Structure (Kustomize)

```
k8s/
├── base/
│   ├── kustomization.yaml
│   ├── namespace-platform.yaml
│   ├── namespace-quant.yaml
│   ├── namespace-finetune.yaml
│   ├── namespace-eval.yaml
│   ├── namespace-observability.yaml
│   ├── namespace-llm-baseline.yaml          # Added for baseline model
│   ├── gateway/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── serviceaccount.yaml
│   ├── quant-api/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── serviceaccount.yaml
│   ├── finetune-api/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── serviceaccount.yaml
│   ├── eval-api/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── serviceaccount.yaml
│   ├── llm-baseline/                         # Added for baseline model
│   │   ├── deployment.yaml                   # vLLM deployment (design-10)
│   │   ├── service.yaml
│   │   ├── pvc.yaml                          # HuggingFace cache
│   │   └── secret.yaml                       # HF token (sealed)
│   └── observability/
│       ├── otel-collector-config.yaml
│       ├── grafana-deployment.yaml
│       └── prometheus-config.yaml
├── overlays/
│   ├── dev/
│   │   ├── kustomization.yaml
│   │   ├── patches/
│   │   │   ├── gateway-replicas.yaml
│   │   │   ├── resource-limits.yaml
│   │   │   └── ingress-dev.yaml
│   │   └── secrets/
│   │       └── sealed-secrets.yaml
│   ├── staging/
│   │   └── kustomization.yaml
│   └── prod/
│       ├── kustomization.yaml
│       ├── patches/
│       │   ├── gateway-replicas.yaml
│       │   ├── resource-limits.yaml
│       │   ├── hpa.yaml
│       │   └── pdb.yaml
│       └── secrets/
│           └── sealed-secrets.yaml
└── scripts/
    ├── apply.sh
    ├── diff.sh
    └── rollback.sh
```

---

## Namespace Definitions

### Platform Namespace

```yaml
# base/namespace-platform.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: platform
  labels:
    app.kubernetes.io/managed-by: kustomize
    tier: platform
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: platform-quota
  namespace: platform
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "20"
    services: "10"
    configmaps: "20"
    secrets: "20"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: platform-limits
  namespace: platform
spec:
  limits:
    - type: Container
      default:
        cpu: 500m
        memory: 512Mi
      defaultRequest:
        cpu: 100m
        memory: 128Mi
      max:
        cpu: "2"
        memory: 4Gi
      min:
        cpu: 50m
        memory: 64Mi
```

### Team Namespace (Example: Quant)

```yaml
# base/namespace-quant.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: quant
  labels:
    app.kubernetes.io/managed-by: kustomize
    tier: team
    team: quantization
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: quant-quota
  namespace: quant
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 16Gi
    limits.cpu: "16"
    limits.memory: 32Gi
    pods: "15"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: quant-limits
  namespace: quant
spec:
  limits:
    - type: Container
      default:
        cpu: "1"
        memory: 2Gi
      defaultRequest:
        cpu: 250m
        memory: 512Mi
      max:
        cpu: "4"
        memory: 8Gi
      min:
        cpu: 100m
        memory: 128Mi
```

---

## Probe Strategy

All deployments must implement three probe types with specific purposes:

| Probe Type    | Purpose                             | Behavior                                    |
| ------------- | ----------------------------------- | ------------------------------------------- |
| **Startup**   | Allow slow container initialization | Delays liveness/readiness until app warm up |
| **Liveness**  | Detect deadlocked/crashed processes | Restarts container if fails                 |
| **Readiness** | Gate traffic to healthy instances   | Removes from Service endpoints if fails     |

### Probe Pattern Template

```yaml
# Standard probe configuration for all services
startupProbe:
  httpGet:
    path: /startup # Returns 200 when initialization complete
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 30 # 5s * 30 = 150s max startup time
  successThreshold: 1

livenessProbe:
  httpGet:
    path: /health # Returns 200 if process alive and responsive
    port: 8000
  initialDelaySeconds: 0 # Starts after startup probe succeeds
  periodSeconds: 15
  failureThreshold: 3 # 15s * 3 = 45s to detect dead process
  successThreshold: 1
  timeoutSeconds: 5

readinessProbe:
  httpGet:
    path: /ready # Returns 200 if ready to serve requests
    port: 8000
  initialDelaySeconds: 0 # Starts after startup probe succeeds
  periodSeconds: 5
  failureThreshold: 3 # 5s * 3 = 15s to remove from endpoints
  successThreshold: 1
  timeoutSeconds: 3
```

---

## Controlled Failure Scenarios

### 1. Probe Restart (Liveness Failure)

**Scenario**: Container deadlocks, liveness probe fails, Kubernetes restarts pod.

**Expected Behavior**:

1. Liveness probe fails 3 consecutive times (45s)
2. Kubernetes terminates container
3. Container restarts with `restartCount` incremented
4. Startup probe runs again
5. Traffic resumes after readiness succeeds

**Test Command**:

```bash
# Trigger deadlock in quant-api and watch restart
kubectl exec -n quant deploy/quant-api -- curl -X POST localhost:8000/debug/deadlock

# Watch pod restart
kubectl get pods -n quant -w

# Verify restartCount incremented
kubectl get pods -n quant -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}'
```

### 2. Quota Rejection

**Scenario**: Deploy exceeds namespace ResourceQuota, request rejected.

**Expected Behavior**:

1. Deployment attempts to scale beyond quota
2. Kubernetes rejects pod creation with quota exceeded event
3. Existing pods remain running (no disruption)
4. Event logged in namespace

**Test Command**:

```bash
# Attempt to deploy more pods than quota allows
kubectl -n quant scale deployment/quant-api --replicas=50

# Check events for quota rejection
kubectl get events -n quant --field-selector reason=FailedCreate

# Verify quota status
kubectl describe resourcequota quant-quota -n quant
```

### 3. Readiness-Gated Traffic

**Scenario**: Pod starts but is not yet ready, traffic routes only to ready pods.

**Expected Behavior**:

1. New pod created during rolling update
2. Startup probe succeeds
3. Readiness probe initially fails (e.g., cache warming)
4. Traffic continues to old pods only
5. Readiness succeeds, traffic shifts to new pod
6. Old pod terminates after new is ready

**Test Command**:

```bash
# Watch rolling update with readiness gates
kubectl rollout restart deployment/quant-api -n quant

# Watch endpoints - only ready pods listed
kubectl get endpoints quant-api -n quant -w

# Verify service routes to ready pods only
kubectl describe endpoints quant-api -n quant
```

---

## Gateway Deployment

```yaml
# base/gateway/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway
  namespace: platform
  labels:
    app: gateway
    component: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: gateway
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: gateway
        component: api
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: gateway-sa
      terminationGracePeriodSeconds: 30
      containers:
        - name: gateway
          image: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev/gateway:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
              name: http
              protocol: TCP

          # Environment from ConfigMap
          envFrom:
            - configMapRef:
                name: gateway-config

          # Probe configuration
          startupProbe:
            httpGet:
              path: /startup
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 30

          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 15
            failureThreshold: 3
            timeoutSeconds: 5

          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            periodSeconds: 5
            failureThreshold: 3
            timeoutSeconds: 3

          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 1Gi

          securityContext:
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 1000
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL

      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: gateway
                topologyKey: kubernetes.io/hostname
---
# base/gateway/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: gateway
  namespace: platform
  labels:
    app: gateway
spec:
  type: ClusterIP
  selector:
    app: gateway
  ports:
    - port: 80
      targetPort: 8000
      protocol: TCP
      name: http
---
# base/gateway/serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gateway-sa
  namespace: platform
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws:iam::ACCOUNT_ID:role/llmplatform-dev-gateway-irsa"
---
# base/gateway/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gateway-config
  namespace: platform
data:
  LOG_LEVEL: "INFO"
  AWS_REGION: "us-west-2"
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector.observability.svc.cluster.local:4317"
  OTEL_SERVICE_NAME: "gateway"

  # Team service endpoints (K8s DNS)
  QUANT_SERVICE_URL: "http://quant-api.quant.svc.cluster.local"
  FINETUNE_SERVICE_URL: "http://finetune-api.finetune.svc.cluster.local"
  EVAL_SERVICE_URL: "http://eval-api.eval.svc.cluster.local"

  # Routing configuration (JSON)
  ROUTE_TABLE: |
    {
      "quant": {
        "url": "http://quant-api.quant.svc.cluster.local",
        "timeout_ms": 30000
      },
      "finetune": {
        "url": "http://finetune-api.finetune.svc.cluster.local",
        "timeout_ms": 60000,
        "ab_variants": {
          "lora-v1": {"weight": 80},
          "lora-v2": {"weight": 20}
        }
      },
      "eval": {
        "url": "http://eval-api.eval.svc.cluster.local",
        "timeout_ms": 45000
      }
    }
```

> **Port Mapping Note**: The Gateway Service maps port `80 → 8000`. The ALB
> Ingress health-check targets pod IP directly (`target-type: ip`) on port 8000.
> If you later switch to `target-type: instance`, update the health-check port
> accordingly.

---

## Team Service Deployment (Example: quant-api)

```yaml
# base/quant-api/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: quant-api
  namespace: quant
  labels:
    app: quant-api
    team: quantization
spec:
  replicas: 2
  selector:
    matchLabels:
      app: quant-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: quant-api
        team: quantization
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: quant-sa
      terminationGracePeriodSeconds: 30
      containers:
        - name: quant-api
          image: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev/quant-api:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
              name: http

          envFrom:
            - configMapRef:
                name: quant-config

          # Full probe pattern
          startupProbe:
            httpGet:
              path: /startup
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 5
            failureThreshold: 36 # Allow up to 3 minutes for model loading

          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            periodSeconds: 15
            failureThreshold: 3
            timeoutSeconds: 5

          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            periodSeconds: 5
            failureThreshold: 3
            timeoutSeconds: 3

          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: "2"
              memory: 4Gi

          securityContext:
            readOnlyRootFilesystem: true
            runAsNonRoot: true
            runAsUser: 1000
            allowPrivilegeEscalation: false
---
# base/quant-api/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: quant-api
  namespace: quant
  labels:
    app: quant-api
spec:
  type: ClusterIP
  selector:
    app: quant-api
  ports:
    - port: 80
      targetPort: 8000
      protocol: TCP
      name: http
---
# base/quant-api/serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: quant-sa
  namespace: quant
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws:iam::ACCOUNT_ID:role/llmplatform-dev-quant-api-irsa"
---
# base/quant-api/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: quant-config
  namespace: quant
data:
  LOG_LEVEL: "DEBUG"
  AWS_REGION: "us-west-2"
  SAGEMAKER_ENDPOINT_NAME: "quant-endpoint"
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector.observability.svc.cluster.local:4317"
  OTEL_SERVICE_NAME: "quant-api"

  # SageMaker timeout configuration
  SAGEMAKER_TIMEOUT_MS: "30000"

  # Failure handling mode
  ENABLE_FALLBACK: "false"
```

---

## ALB Ingress Controller

### Ingress Resource

```yaml
# overlays/dev/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: platform-ingress
  namespace: platform
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:us-west-2:ACCOUNT_ID:certificate/CERT_ID
    alb.ingress.kubernetes.io/healthcheck-path: /health
    alb.ingress.kubernetes.io/healthcheck-interval-seconds: "15"
    alb.ingress.kubernetes.io/healthcheck-timeout-seconds: "5"
    alb.ingress.kubernetes.io/healthy-threshold-count: "2"
    alb.ingress.kubernetes.io/unhealthy-threshold-count: "3"
spec:
  rules:
    - host: api.llmplatform.dev
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: gateway
                port:
                  number: 80
---
# Grafana Ingress (observability namespace)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: grafana-ingress
  namespace: observability
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
spec:
  rules:
    - host: grafana.llmplatform.dev
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: grafana
                port:
                  number: 3000
```

---

## Kustomization Files

### Base Kustomization

```yaml
# base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  # Namespaces (6 total)
  - namespace-platform.yaml
  - namespace-quant.yaml
  - namespace-finetune.yaml
  - namespace-eval.yaml
  - namespace-observability.yaml
  - namespace-llm-baseline.yaml # vLLM baseline model (design-10)

  # Gateway
  - gateway/deployment.yaml
  - gateway/service.yaml
  - gateway/serviceaccount.yaml
  - gateway/configmap.yaml

  # Team services
  - quant-api/deployment.yaml
  - quant-api/service.yaml
  - quant-api/serviceaccount.yaml
  - quant-api/configmap.yaml

  - finetune-api/deployment.yaml
  - finetune-api/service.yaml
  - finetune-api/serviceaccount.yaml
  - finetune-api/configmap.yaml

  - eval-api/deployment.yaml
  - eval-api/service.yaml
  - eval-api/serviceaccount.yaml
  - eval-api/configmap.yaml

  # Baseline model (see design-10-models.md)
  - llm-baseline/deployment.yaml
  - llm-baseline/service.yaml
  - llm-baseline/pvc.yaml

commonLabels:
  app.kubernetes.io/managed-by: kustomize
  app.kubernetes.io/part-of: llm-optimization-platform
```

### Dev Overlay

```yaml
# overlays/dev/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base
  - ingress.yaml

commonLabels:
  environment: dev

# Image tags for dev
images:
  - name: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev/gateway
    newTag: dev-latest
  - name: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev/quant-api
    newTag: dev-latest
  - name: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev/finetune-api
    newTag: dev-latest
  - name: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev/eval-api
    newTag: dev-latest

# Dev-specific patches
patches:
  - path: patches/gateway-replicas.yaml
  - path: patches/resource-limits.yaml

configMapGenerator:
  - name: gateway-config
    behavior: merge
    literals:
      - LOG_LEVEL=DEBUG
```

### Prod Overlay

```yaml
# overlays/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base
  - ingress.yaml
  - hpa.yaml
  - pdb.yaml

commonLabels:
  environment: prod

replicas:
  - name: gateway
    count: 4
  - name: quant-api
    count: 3
  - name: finetune-api
    count: 3
  - name: eval-api
    count: 3

images:
  - name: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-prod/gateway
    newTag: v1.0.0
  - name: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-prod/quant-api
    newTag: v1.0.0
  - name: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-prod/finetune-api
    newTag: v1.0.0
  - name: ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-prod/eval-api
    newTag: v1.0.0

configMapGenerator:
  - name: gateway-config
    behavior: merge
    literals:
      - LOG_LEVEL=INFO
```

---

## HPA and PDB (Production)

### Horizontal Pod Autoscaler

```yaml
# overlays/prod/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: gateway-hpa
  namespace: platform
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: gateway
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
```

### Pod Disruption Budget

```yaml
# overlays/prod/pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: gateway-pdb
  namespace: platform
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: gateway
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: quant-api-pdb
  namespace: quant
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: quant-api
```

---

## Deployment Commands

### Apply to Environment

```bash
# Dev
kubectl apply -k k8s/overlays/dev

# Prod
kubectl apply -k k8s/overlays/prod
```

### Preview Changes

```bash
# Show what will be applied
kubectl diff -k k8s/overlays/dev
```

### Rollback

```bash
# Rollback specific deployment
kubectl rollout undo deployment/gateway -n platform

# Rollback to specific revision
kubectl rollout undo deployment/gateway -n platform --to-revision=2
```

### Status Checks

```bash
# Check all pods across namespaces
kubectl get pods -A -l app.kubernetes.io/part-of=llm-optimization-platform

# Check deployment status
kubectl rollout status deployment/gateway -n platform

# Check readiness endpoints
kubectl get endpoints -A | grep -E 'gateway|quant|finetune|eval'
```

---

## Implementation Checklist

- [ ] Create all namespace YAML files with ResourceQuotas and LimitRanges
- [ ] Create Gateway deployment with full probe pattern
- [ ] Create team service deployments (quant, finetune, eval)
- [ ] Configure ServiceAccounts with IRSA annotations
- [ ] Create ConfigMaps with OTEL and routing configuration
- [ ] Configure Kustomize base and overlays
- [ ] Deploy ALB Ingress Controller to cluster
- [ ] Create Ingress resources for Gateway and Grafana
- [ ] Test probe restart scenario
- [ ] Test quota rejection scenario
- [ ] Test readiness-gated traffic during rolling update
- [ ] Configure HPA and PDB for production
