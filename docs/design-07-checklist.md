# Design Document 7: Done Means Done - Acceptance Checklist

## Overview

This document defines the **acceptance criteria** for marking the LLM Optimization Platform as "done". Each section must be verified before the platform is considered production-ready.

---

## Implementation Order (Vibe Coding Sequence)

For fastest "first working state", follow this sequence:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 1: Foundation (Day 1)                                                 │
│  ├── design-01: Terraform init/plan/apply                                   │
│  └── design-02: kubectl apply namespaces                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Phase 2: Observability (Day 1-2)                                           │
│  ├── design-03: Deploy OTEL Collector, Prometheus, Grafana                  │
│  └── design-08: Verify attribute schema in traces                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  Phase 3: Services (Day 2-3)                                                │
│  ├── design-10: Deploy baseline model (vLLM)                                │
│  ├── design-04: Deploy team services + gateway                              │
│  └── design-05: Set up CI/CD workflows                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  Phase 4: Polish (Day 3-4)                                                  │
│  ├── design-06: Build and install Grafana plugin                            │
│  ├── design-09: Generate promptsets, run canary suite                       │
│  └── design-07: Run acceptance checklist                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**First Request Working**: After Phase 3, you should be able to:

```bash
curl -X POST "http://gateway/api/quant/predict" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello", "max_tokens": 10}'
```

---

## Quality Areas Weight Distribution

| Quality Area             | Weight | Primary Design Document     |
| ------------------------ | ------ | --------------------------- |
| Terraform IaC            | 15%    | design-01-infrastructure.md |
| Kubernetes Orchestration | 20%    | design-02-kubernetes.md     |
| Observability Stack      | 12%    | design-03-observability.md  |
| SageMaker Integration    | 15%    | design-04-sagemaker.md      |
| GitHub Actions CI/CD     | 12%    | design-05-cicd.md           |
| Operations Dashboard     | 5%     | design-06-dashboard.md      |
| OTel Attribute Schema    | 6%     | design-08-otel-schema.md    |
| Data Engine              | 8%     | design-09-data-engine.md    |
| Baseline Model           | 7%     | design-10-models.md         |

---

## 1. Infrastructure (Terraform) - 15%

### 1.1 Core Resources

- [ ] VPC created with public and private subnets (3 AZs)
- [ ] NAT gateways provisioned for private subnet egress
- [ ] EKS cluster provisioned and accessible
- [ ] Node groups created with appropriate instance types
- [ ] ECR repositories created for all services (gateway, quant-api, finetune-api, eval-api)

### 1.2 State Management

- [ ] S3 bucket created for Terraform state with versioning enabled
- [ ] DynamoDB table created for state locking
- [ ] Backend configuration verified (`terraform init` succeeds)

### 1.3 IAM & Security

- [ ] EKS cluster IAM role with required policies
- [ ] Node group IAM role with ECR, EKS worker policies
- [ ] OIDC provider created for IRSA
- [ ] GitHub OIDC provider configured
- [ ] GitHub Actions IAM role with scoped permissions

### 1.4 IRSA Roles

- [ ] IRSA role for Gateway service
- [ ] IRSA role for Quant API (SageMaker invoke)
- [ ] IRSA role for Finetune API (SageMaker invoke)
- [ ] IRSA role for Eval API (SageMaker invoke)

### 1.5 Team-Facing Outputs

- [ ] `eks_cluster_name` output available
- [ ] `ecr_repository_urls` output available
- [ ] `irsa_role_arns` output available
- [ ] `terraform output` produces valid JSON

### Verification Commands

```bash
# Verify outputs
cd infra/envs/dev && terraform output -json | jq .

# Verify cluster access
aws eks update-kubeconfig --name $(terraform output -raw eks_cluster_name)
kubectl get nodes

# Verify ECR access
aws ecr describe-repositories --query 'repositories[].repositoryName'
```

---

## 2. Kubernetes Orchestration - 20%

### 2.1 Namespace Structure

- [ ] `platform` namespace exists with ResourceQuota and LimitRange
- [ ] `quant` namespace exists with ResourceQuota and LimitRange
- [ ] `finetune` namespace exists with ResourceQuota and LimitRange
- [ ] `eval` namespace exists with ResourceQuota and LimitRange
- [ ] `observability` namespace exists with ResourceQuota and LimitRange
- [ ] `llm-baseline` namespace exists (for vLLM model - see design-10)

### 2.2 Deployments

- [ ] Gateway deployment running in `platform` namespace
- [ ] quant-api deployment running in `quant` namespace
- [ ] finetune-api deployment running in `finetune` namespace
- [ ] eval-api deployment running in `eval` namespace

### 2.3 Probe Coverage

For each deployment:

- [ ] `startupProbe` configured with appropriate `failureThreshold`
- [ ] `livenessProbe` configured with appropriate `periodSeconds`
- [ ] `readinessProbe` configured with appropriate `periodSeconds`

### 2.4 ServiceAccounts & IRSA

- [ ] Each deployment uses dedicated ServiceAccount
- [ ] ServiceAccounts annotated with appropriate IRSA role ARN
- [ ] Pods can assume IAM role (verify with STS)

### 2.5 Services & Networking

- [ ] ClusterIP services created for all deployments
- [ ] ALB Ingress Controller deployed
- [ ] Ingress resource routes to Gateway
- [ ] Gateway accessible via ALB URL

### 2.6 Controlled Failure Scenarios

#### Probe Restart Test

```bash
# Trigger liveness failure and verify restart
kubectl exec -n quant deploy/quant-api -- kill -9 1 || true
sleep 60
kubectl get pods -n quant -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}'
# Expected: restartCount > 0
```

- [ ] Pod restarts when liveness probe fails
- [ ] Pod becomes ready after restart

#### Quota Rejection Test

```bash
# Attempt to exceed quota
kubectl -n quant scale deployment/quant-api --replicas=100
kubectl get events -n quant --field-selector reason=FailedCreate | head -5
# Expected: quota exceeded events
kubectl -n quant scale deployment/quant-api --replicas=2  # Reset
```

- [ ] Deployment scale blocked by quota
- [ ] Existing pods remain running

#### Readiness-Gated Traffic Test

```bash
# Watch endpoints during rolling restart
kubectl rollout restart deployment/gateway -n platform
kubectl get endpoints gateway -n platform -w
# Expected: endpoints update as pods become ready
```

- [ ] Traffic routes only to ready pods
- [ ] No traffic to unready pods during rollout

### Verification Commands

```bash
# Check all namespaces
kubectl get ns -l app.kubernetes.io/managed-by=kustomize

# Check all deployments
kubectl get deployments -A -l app.kubernetes.io/part-of=llm-optimization-platform

# Check probes configured
kubectl get deployment -n platform gateway -o jsonpath='{.spec.template.spec.containers[0].startupProbe}'
kubectl get deployment -n platform gateway -o jsonpath='{.spec.template.spec.containers[0].livenessProbe}'
kubectl get deployment -n platform gateway -o jsonpath='{.spec.template.spec.containers[0].readinessProbe}'

# Check IRSA annotation
kubectl get sa -n quant quant-sa -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}'
```

---

## 3. Observability Stack - 12%

### 3.1 OTEL Collector

- [ ] OTEL Collector deployed in `observability` namespace
- [ ] OTLP receiver configured (gRPC :4317, HTTP :4318)
- [ ] Metrics pipeline exports to Prometheus
- [ ] Logs pipeline exports to Loki
- [ ] Traces pipeline exports to Tempo

### 3.2 Prometheus/Mimir

- [ ] Prometheus deployed and scraping targets
- [ ] Remote write enabled
- [ ] Retention configured (15d)

### 3.3 Loki

- [ ] Loki deployed and accepting logs
- [ ] Log retention configured

### 3.4 Tempo

- [ ] Tempo deployed and accepting traces
- [ ] OTLP receiver enabled

### 3.5 Grafana

- [ ] Grafana deployed with datasources provisioned
- [ ] Prometheus datasource configured
- [ ] Loki datasource configured
- [ ] Tempo datasource configured
- [ ] Log-to-trace correlation working

### 3.6 Service Instrumentation

- [ ] Gateway emits OTEL telemetry
- [ ] quant-api emits OTEL telemetry
- [ ] finetune-api emits OTEL telemetry
- [ ] eval-api emits OTEL telemetry

### 3.7 Trace Flow Verification

- [ ] Request traces visible: Gateway → Team Service → SageMaker
- [ ] Correlation IDs propagate through call chain
- [ ] Traces visible in Tempo

### Verification Commands

```bash
# Check OTEL Collector
kubectl get pods -n observability -l app=otel-collector
kubectl logs -n observability -l app=otel-collector --tail=20

# Check Prometheus targets
kubectl port-forward -n observability svc/prometheus 9090:9090 &
curl -s localhost:9090/api/v1/targets | jq '.data.activeTargets | length'

# Check Grafana datasources
kubectl port-forward -n observability svc/grafana 3000:3000 &
curl -s -u admin:PASSWORD localhost:3000/api/datasources | jq '.[].name'

# Generate trace and verify
curl -X POST "http://gateway/api/quant/predict" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: test-trace-001" \
  -d '{"prompt": "test", "max_tokens": 5}'
# Then verify trace in Tempo with trace_id
```

---

## 4. SageMaker Integration - 15%

### 4.1 Team Service Endpoints

For each team service (quant-api, finetune-api, eval-api):

- [ ] `GET /health` returns 200 when process alive
- [ ] `GET /ready` returns 200 when ready for traffic
- [ ] `GET /startup` returns 200 when initialization complete
- [ ] `POST /predict` accepts request and returns response

### 4.2 SageMaker Client

- [ ] Timeout configuration implemented
- [ ] Error propagation works (non-fallback mode)
- [ ] Fallback response works (fallback mode)
- [ ] OTEL tracing wraps SageMaker calls

### 4.3 Gateway Routing

- [ ] Route table parses correctly from ConfigMap
- [ ] Requests route to correct team service
- [ ] Timeout per team configurable

### 4.4 A/B Routing (finetune)

- [ ] A/B variants configured in route table
- [ ] Variant selection based on weights
- [ ] `X-Route-Variant` header in response

### 4.5 Response Headers

- [ ] `X-Correlation-ID` echoed in response
- [ ] `X-Route-Team` indicates handling team
- [ ] `X-Route-Variant` indicates selected variant
- [ ] `X-Latency-Ms` indicates request latency

### 4.6 SageMaker Timeout Test

```bash
# Test timeout handling (if endpoint is slow)
curl -X POST "http://gateway/api/quant/predict" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: test-timeout-001" \
  -d '{"prompt": "test with very long generation", "max_tokens": 10000}'
# Expected: 504 timeout OR fallback response
```

- [ ] Timeout produces 504 when fallback disabled
- [ ] Timeout produces fallback when fallback enabled

### Verification Commands

```bash
# Test each team endpoint
for TEAM in quant finetune eval; do
  echo "Testing $TEAM..."
  curl -s "http://gateway/api/$TEAM/predict" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: acceptance-$TEAM" \
    -d '{"prompt": "Test", "max_tokens": 5}' | jq .
done

# Check response headers
curl -si "http://gateway/api/quant/predict" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Test", "max_tokens": 5}' | grep -E "^X-"
```

---

## 5. GitHub Actions CI/CD - 12%

### 5.1 OIDC Authentication

- [ ] GitHub OIDC provider exists in AWS
- [ ] GitHub Actions IAM role exists with correct trust policy
- [ ] Role assumption works from GitHub Actions

### 5.2 CI Pipeline

- [ ] Lint job runs on PR
- [ ] Test job runs on PR
- [ ] Build job runs for each service
- [ ] Push job pushes to correct ECR repository
- [ ] Image scan runs after push

### 5.3 CD Pipeline

- [ ] Deploy to dev runs on develop branch merge
- [ ] Deploy to prod runs on main branch merge
- [ ] Kustomize applies correct image tags
- [ ] Rollout status verified after deploy

### 5.4 Terraform Pipeline

- [ ] Format check runs on infra/\*\* changes
- [ ] Plan runs and comments on PR
- [ ] Apply runs only on main merge
- [ ] Destroy requires manual approval

### 5.5 Rollback

- [ ] Rollback workflow exists
- [ ] Rollback to previous revision works
- [ ] Rollback to specific revision works

### Verification Commands

```bash
# Verify GitHub Actions IAM role
aws iam get-role --role-name llmplatform-github-actions --query 'Role.AssumeRolePolicyDocument'

# Verify ECR images pushed
aws ecr describe-images \
  --repository-name llmplatform-dev/gateway \
  --query 'imageDetails[*].imageTags' | head -10

# Check deployment history
kubectl rollout history deployment/gateway -n platform
```

### 5.6 Workflow Runs Verification

- [ ] CI workflow completes successfully on PR
- [ ] CD workflow deploys to dev successfully
- [ ] CD workflow deploys to prod successfully (with approval)
- [ ] Rollback workflow executes successfully

---

## 6. Operations Dashboard - 5%

### 6.1 Gateway Ops API

- [ ] `GET /ops/services` returns service list
- [ ] `GET /ops/health` returns team health status
- [ ] `GET /ops/stats` returns 24h statistics
- [ ] `POST /ops/test` executes test prediction

### 6.2 Grafana Plugin

- [ ] Plugin builds without errors
- [ ] Plugin installs in Grafana
- [ ] Plugin renders service table
- [ ] Plugin renders health overview
- [ ] Plugin renders stats cards
- [ ] Plugin test console works

### 6.3 Dashboard Configuration

- [ ] Dashboard created with plugin panel
- [ ] Prometheus panels show request metrics
- [ ] Loki panel shows recent logs
- [ ] Dashboard auto-refreshes (30s)

### Verification Commands

```bash
# Test ops API endpoints
curl -s "http://gateway/ops/services" | jq .
curl -s "http://gateway/ops/health" | jq .
curl -s "http://gateway/ops/stats" | jq .

# Test prediction via ops API
curl -s -X POST "http://gateway/ops/test" \
  -H "Content-Type: application/json" \
  -d '{"team": "quant", "prompt": "Test", "max_tokens": 5}' | jq .

# Verify Grafana plugin
curl -s -u admin:PASSWORD "http://grafana:3000/api/plugins" | jq '.[].id' | grep llmplatform
```

---

## 7. OTel Attribute Schema - 6%

### 7.1 Resource Attributes

- [ ] All services set `service.name` correctly
- [ ] All services set `service.version` from build
- [ ] `lab.team` attribute set correctly per service
- [ ] `k8s.namespace.name` populated from pod metadata

### 7.2 Gateway Span Attributes

- [ ] `lab.route.target.team` set on ingress spans
- [ ] `lab.route.decision` set (`direct`, `fallback`, `deny`)
- [ ] `lab.ab.bucket` set when A/B testing active
- [ ] `lab.timeout.ms` set per backend call

### 7.3 Team Service Span Attributes

- [ ] `genai.operation.name` set to `chat` or `completion`
- [ ] `genai.request.model` set correctly
- [ ] `genai.usage.input_tokens` captured
- [ ] `genai.usage.output_tokens` captured
- [ ] `lab.sagemaker.endpoint` set for SageMaker calls

### 7.4 Cardinality Safety

- [ ] No raw prompts/responses in metric labels
- [ ] `genai.prompt.hash` used instead of full prompt
- [ ] High-cardinality values confined to trace attributes only

### Verification Commands

```bash
# Verify span attributes in Tempo
curl -s "http://tempo:3200/api/search?q=lab.route.target.team=quant" | jq '.traces[0]'

# Verify resource attributes
kubectl exec -n quant deploy/quant-api -- \
  curl -s localhost:8000/debug/otel-config | jq '.resource_attributes'
```

---

## 8. Data Engine - 8%

### 8.1 Promptset Files

- [ ] Canary promptset exists (50-200 prompts)
- [ ] Performance promptset exists (500-2000 prompts)
- [ ] Quant-sensitivity promptset exists
- [ ] Domain promptset exists with train/eval/canary splits
- [ ] Eval rubric set exists

### 8.2 Test Harness

- [ ] `run_canary_suite()` function works
- [ ] `run_performance_suite()` function works
- [ ] Results include `lab.promptset.id` attribute
- [ ] Results include `lab.run.id` attribute

### 8.3 Controlled Failures

- [ ] Timeout scenario promptset exists
- [ ] Large payload promptset exists
- [ ] Malformed input promptset exists
- [ ] Rate limit burst promptset exists
- [ ] Expected error responses documented

### 8.4 S3 Storage

- [ ] Promptsets versioned in S3
- [ ] Manifest files exist per promptset
- [ ] Promptset download works from services

### Verification Commands

```bash
# List promptsets in S3
aws s3 ls s3://llmplatform-data/promptsets/

# Run canary suite
curl -s -X POST "http://gateway/test/canary" \
  -H "Content-Type: application/json" | jq '.summary'

# Check test harness results
curl -s "http://gateway/test/results?run_id=latest" | jq '.pass_rate'
```

---

## 9. Baseline Model - 7%

### 9.1 vLLM Deployment

- [ ] vLLM deployment running in `llm-baseline` namespace
- [ ] Pod has GPU resource allocated
- [ ] HuggingFace cache PVC mounted
- [ ] HF token secret mounted

### 9.2 Service Availability

- [ ] Service responds on port 8000
- [ ] `/v1/models` returns Mistral-7B-Instruct-v0.2
- [ ] `/v1/chat/completions` works
- [ ] `/metrics` endpoint returns Prometheus metrics

### 9.3 Probe Configuration

- [ ] Startup probe allows 7.5 minute cold start
- [ ] Readiness probe gates traffic correctly
- [ ] Liveness probe detects unhealthy state

### 9.4 Team Integration

- [ ] Gateway can route to baseline model
- [ ] quant-api can call baseline for comparison
- [ ] finetune-api uses baseline as control
- [ ] eval-api uses baseline as judge endpoint

### 9.5 Observability

- [ ] Prometheus scrapes vLLM `/metrics`
- [ ] Queue depth metrics visible in Grafana
- [ ] TTFT metrics visible in Grafana

### Verification Commands

```bash
# Check vLLM pod status
kubectl get pods -n llm-baseline -o wide

# Test model endpoint
curl -s "http://mistral-7b-baseline.llm-baseline.svc:8000/v1/models" | jq .

# Test chat completion
curl -s "http://mistral-7b-baseline.llm-baseline.svc:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistralai/Mistral-7B-Instruct-v0.2",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }' | jq '.choices[0].message.content'

# Check metrics
curl -s "http://mistral-7b-baseline.llm-baseline.svc:8000/metrics" | grep vllm_
```

---

## Final Acceptance Sign-Off

### Pre-Sign-Off Checklist

- [ ] All verification commands executed successfully
- [ ] All controlled failure scenarios pass
- [ ] Documentation reviewed and complete
- [ ] No critical security vulnerabilities
- [ ] Performance under expected load verified

### Sign-Off Table

| Quality Area          | Weight | Status | Verified By | Date |
| --------------------- | ------ | ------ | ----------- | ---- |
| Terraform IaC         | 15%    | [ ]    |             |      |
| Kubernetes            | 20%    | [ ]    |             |      |
| Observability         | 12%    | [ ]    |             |      |
| SageMaker Integration | 15%    | [ ]    |             |      |
| CI/CD                 | 12%    | [ ]    |             |      |
| Dashboard             | 5%     | [ ]    |             |      |
| OTel Schema           | 6%     | [ ]    |             |      |
| Data Engine           | 8%     | [ ]    |             |      |
| Baseline Model        | 7%     | [ ]    |             |      |
| **TOTAL**             | 100%   | [ ]    |             |      |

### Final Approval

```
Platform Ready for Production: [ ] YES  [ ] NO

Approver: _______________________
Date: _______________________
Notes: _______________________
```

---

## Quick Reference: Key Verification Commands

```bash
#!/bin/bash
# acceptance-test.sh - Run all acceptance verification commands

echo "=== 1. Infrastructure ==="
terraform -chdir=infra/envs/dev output -json | jq 'keys'

echo "=== 2. Kubernetes ==="
kubectl get ns -l app.kubernetes.io/managed-by=kustomize -o name
kubectl get deployments -A -l app.kubernetes.io/part-of=llm-optimization-platform
kubectl get pods -A -l app.kubernetes.io/part-of=llm-optimization-platform

echo "=== 3. Observability ==="
kubectl get pods -n observability
kubectl logs -n observability -l app=otel-collector --tail=5

echo "=== 4. SageMaker Integration ==="
for ns in quant finetune eval; do
  echo "Testing $ns..."
  kubectl exec -n $ns deploy/$ns-api -- curl -s localhost:8000/health
done

echo "=== 5. Gateway Ops API ==="
curl -s "http://gateway/ops/services" | jq '.[].name'
curl -s "http://gateway/ops/health" | jq '.[] | {team, status}'

echo "=== 6. Controlled Failure: Probe Restart ==="
RESTART_BEFORE=$(kubectl get pods -n quant -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}')
kubectl exec -n quant deploy/quant-api -- curl -X POST localhost:8000/debug/crash || true
sleep 60
RESTART_AFTER=$(kubectl get pods -n quant -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}')
echo "Restarts: Before=$RESTART_BEFORE After=$RESTART_AFTER"

echo "=== Complete ==="
```

---

## Appendix: Known Issues and Workarounds

| Issue | Workaround | Status |
| ----- | ---------- | ------ |
| -     | -          | -      |

_Add any known issues discovered during testing and their workarounds._
