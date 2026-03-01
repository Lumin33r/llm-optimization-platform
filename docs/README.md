# LLM Optimization Platform — Startup Guide

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Repository Layout](#repository-layout)
- [Phase 1 — Provision Infrastructure (Terraform)](#phase-1--provision-infrastructure-terraform)
- [Phase 2 — Deploy Kubernetes Base (Kustomize)](#phase-2--deploy-kubernetes-base-kustomize)
- [Phase 3 — Deploy the Observability Stack](#phase-3--deploy-the-observability-stack)
- [Phase 4 — Deploy the Model Fleet (vLLM / Mistral-7B × 4 variants)](#phase-4--deploy-the-model-fleet-vllm--mistral-7b--4-variants)
- [Phase 5 — Build & Deploy Application Services](#phase-5--build--deploy-application-services)
- [Phase 6 — First End-to-End Request](#phase-6--first-end-to-end-request)
- [Phase 7 — Grafana Plugin & Dashboard](#phase-7--grafana-plugin--dashboard)
- [Phase 8 — Data Engine & Test Harness](#phase-8--data-engine--test-harness)
- [Phase 9 — CI/CD (GitHub Actions)](#phase-9--cicd-github-actions)
- [Validation Scripts](#validation-scripts)
- [Environment Variables Reference](#environment-variables-reference)
- [Service URLs & Ports](#service-urls--ports)
- [Troubleshooting](#troubleshooting)
- [Teardown](#teardown)
- [Design Documents](#design-documents)

---

## Overview

A multi-team platform for optimizing LLM inference on AWS EKS, supporting three internal AI lab teams:

| Team         | Focus                | SageMaker Endpoint  | Model Type            |
| ------------ | -------------------- | ------------------- | --------------------- |
| **Quant**    | Quantization (4-bit) | `quant-endpoint`    | GPTQ / AWQ compressed |
| **FineTune** | LoRA adapters        | `finetune-endpoint` | Fine-tuned variants   |
| **Eval**     | Quality scoring      | `eval-endpoint`     | Evaluation / Judge    |

All teams share a **vLLM-based model fleet** (4 Mistral-7B variants on dedicated SPOT GPU nodes). Each team has a dedicated model: AWQ (quant), LoRA-enabled (finetune), Judge (eval), and FP16 (reference baseline). Observability is provided end-to-end via OpenTelemetry → Prometheus / Loki / Tempo → Grafana.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                               AWS  us-west-2                                    │
│                                                                                 │
│  ┌────────────── EKS Cluster (v1.29) ───────────────────────────────────────┐  │
│  │                    6 Kubernetes Namespaces                                │  │
│  │                                                                          │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                    │  │
│  │  │ platform │ │  quant   │ │ finetune │ │   eval   │                    │  │
│  │  │ Gateway  │→│ quant-api│ │finetune- │ │ eval-api │                    │  │
│  │  │ :8000    │ │ :8000    │ │ api:8000 │ │ :8000    │                    │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘                    │  │
│  │                                                                          │  │
│  │  ┌────────────────────┐  ┌──────────────────────────┐                    │  │
│  │  │  observability     │  │     llm-baseline          │                    │  │
│  │  │  OTEL Collector    │  │  vLLM v0.6.6              │                    │  │
│  │  │  Prometheus :9090  │  │  Mistral-7B-v0.2-AWQ     │                    │  │
│  │  │  Loki / Tempo      │  │  GPU: g4dn.xlarge (T4)   │                    │  │
│  │  │  Grafana :3000     │  │  :8000                    │                    │  │
│  │  └────────────────────┘  └──────────────────────────┘                    │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌──────────────────────┐  ┌─────────────────────────────┐                     │
│  │  SageMaker Endpoints │  │  ECR Repositories            │                     │
│  │  quant-endpoint      │  │  llmplatform-dev/gateway     │                     │
│  │  finetune-endpoint   │  │  llmplatform-dev/quant-api   │                     │
│  │  eval-endpoint       │  │  llmplatform-dev/finetune-api│                     │
│  └──────────────────────┘  │  llmplatform-dev/eval-api    │                     │
│                             └─────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required Tools

| Tool        | Minimum Version | Install                                                                                                                   |
| ----------- | --------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `aws`       | 2.x             | `curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscli.zip && unzip awscli.zip && sudo ./aws/install` |
| `terraform` | >= 1.5.0        | `tfenv install 1.6.0 && tfenv use 1.6.0`                                                                                  |
| `kubectl`   | >= 1.29         | `curl -LO "https://dl.k8s.io/release/v1.29.0/bin/linux/amd64/kubectl"`                                                    |
| `kustomize` | >= 5.0          | `kubectl` includes it (`kubectl apply -k`)                                                                                |
| `docker`    | >= 24.x         | System package manager                                                                                                    |
| `node`      | >= 18.x         | `nvm install 18` (for Grafana plugin)                                                                                     |
| `python`    | >= 3.11         | System or `pyenv install 3.11`                                                                                            |

### Required Accounts & Secrets

| Secret                  | Where Used                  | How to Get                                    |
| ----------------------- | --------------------------- | --------------------------------------------- |
| **AWS Account ID**      | Terraform, CI/CD            | `aws sts get-caller-identity --query Account` |
| **AWS IAM credentials** | Terraform apply             | IAM user or SSO with `AdministratorAccess`    |
| **HuggingFace Token**   | vLLM baseline model (gated) | https://huggingface.co/settings/tokens        |
| **GitHub OIDC Role**    | CI/CD pipeline              | Created by `github_oidc` Terraform module     |

### Required AWS Permissions

The deploying IAM principal needs permissions for: VPC, EKS, ECR, SageMaker, IAM (roles/policies), S3, DynamoDB (for TF state), and CloudWatch.

---

## Repository Layout

```
llm-optimization-platform/
├── .github/workflows/       # CI/CD pipelines
│   ├── ci-cd.yaml           #   Build → push → deploy (4 services)
│   ├── terraform.yaml        #   Infra plan/apply/destroy
│   ├── rollback.yaml         #   Emergency rollback
│   └── post-deploy-smoke.yaml
│
├── infra/                   # Terraform IaC
│   ├── modules/             #   8 reusable modules
│   │   ├── vpc/             #     VPC, subnets, NAT
│   │   ├── eks/             #     EKS cluster + node groups
│   │   ├── ecr/             #     Container registries
│   │   ├── iam_irsa/        #     IAM Roles for Service Accounts
│   │   ├── k8s_namespaces/  #     Namespace configs + quotas
│   │   ├── sagemaker_endpoints/  # Team endpoints
│   │   ├── github_oidc/     #     OIDC provider for GitHub Actions
│   │   └── observability/   #     Log groups, dashboards
│   └── envs/dev/            #   Dev environment root module
│       ├── main.tf
│       ├── variables.tf
│       └── terraform.tfvars
│
├── k8s/                     # Kubernetes manifests (Kustomize)
│   ├── base/                #   Base resources
│   │   ├── kustomization.yaml
│   │   ├── gateway/         #     API gateway deployment
│   │   ├── quant-api/       #     Quantization team service
│   │   ├── finetune-api/    #     Fine-tuning team service
│   │   ├── eval-api/        #     Evaluation team service
│   │   ├── observability/   #     OTEL, Prometheus, Loki, Tempo, Grafana
│   │   └── llm-baseline/    #     vLLM Mistral-7B deployment
│   └── overlays/
│       ├── dev/             #     Dev image tags + patches
│       ├── staging/
│       └── prod/
│
├── services/                # Python FastAPI microservices
│   ├── shared/              #   Common: telemetry, health, models, sagemaker client
│   ├── gateway/             #   API gateway + routing + ops API
│   ├── quant-api/           #   Quantization inference wrapper
│   ├── finetune-api/        #   Fine-tune inference wrapper
│   ├── eval-api/            #   Evaluation scorer + judge
│   ├── data-engine/         #   Promptset generator + S3 API
│   └── test-harness/        #   Load testing / acceptance harness
│
├── grafana-plugins/         # Grafana panel plugin (React/TypeScript)
│   └── llm-platform-ops/
│
├── scripts/                 # Utility scripts
│   ├── golden-checks.sh     #   vLLM baseline health validation
│   ├── failure-demos.sh     #   Controlled failure scenarios
│   ├── quant-comparison.sh  #   Quant vs baseline comparison
│   ├── finetune-ab-test.sh  #   A/B routing test
│   └── validate-autoscaling.sh  # HPA load test
│
├── scenarios/               # Test scenario configs
├── domains/                 # Domain prompt configs
├── prometheus/              # Prometheus alerting rules
└── docs/                    # Design documents (this directory)
```

---

## Phase 1 — Provision Infrastructure (Terraform)

### 1.1 Configure AWS credentials

```bash
# Option A: Environment variables
export AWS_ACCESS_KEY_ID="<your-access-key>"
export AWS_SECRET_ACCESS_KEY="<your-secret-key>"
export AWS_DEFAULT_REGION="us-west-2"

# Option B: AWS SSO
aws sso login --profile <your-profile>
export AWS_PROFILE=<your-profile>

```

### 1.2 Review and customize variables

```bash
cd infra/envs/dev
cat terraform.tfvars
```

Default values:

```hcl
aws_region      = "us-west-2"
project         = "llmplatform"
environment     = "dev"
vpc_cidr        = "10.0.0.0/16"
cluster_version = "1.29"

node_groups = {
  general = {
    instance_types = ["t3.medium"]
    disk_size      = 50
    desired_size   = 2
    min_size       = 1
    max_size       = 4
    labels         = { role = "general" }
    taints         = []
  }
  gpu = {
    instance_types = ["g4dn.xlarge"]
    disk_size      = 100
    desired_size   = 4          # 4 GPU nodes for 4 model variants
    min_size       = 0
    max_size       = 4
    ami_type       = "AL2_x86_64_GPU"  # Required — GPU AMI includes NVIDIA drivers
    capacity_type  = "SPOT"             # ~70% cost savings vs on-demand
    labels         = {
      role                      = "gpu"
      "nvidia.com/gpu.present"  = "true"
    }
    taints = [{
      key    = "nvidia.com/gpu"
      value  = "true"
      effect = "NO_SCHEDULE"
    }]
  }
}
```

> **Note:** GPU nodes use `capacity_type = "SPOT"` for cost savings (~$0.16/hr vs $0.53/hr per node). Spot instances may be reclaimed with 2-minute warning; the Recreate deployment strategy handles this gracefully.

### 1.3 Initialize and apply

```bash
cd infra/envs/dev

# Initialize providers and modules
terraform init

# Review the plan
terraform plan -out=tfplan

# Apply (creates VPC, EKS, ECR, IAM roles, namespaces, SageMaker endpoints)
terraform apply tfplan
```

This provisions:

- **VPC** — `10.0.0.0/16`, 3 AZs, public/private subnets, single NAT gateway
- **EKS** — v1.29 cluster with general + GPU node groups
- **ECR** — 5 repositories: `gateway`, `quant-api`, `finetune-api`, `eval-api`, `grafana-plugin`
- **IAM IRSA** — Per-team roles (SageMaker invoke) + gateway role (CloudWatch)
- **Namespaces** — 6 namespaces with resource quotas and limit ranges
- **SageMaker Endpoints** — `quant-endpoint`, `finetune-endpoint`, `eval-endpoint`
- **GitHub OIDC** — `llmplatform-github-actions` role for CI/CD

### 1.5 Install required cluster addons

The EBS CSI driver is required for PersistentVolumeClaims on EKS 1.29+:

```bash
# Create IAM role for EBS CSI driver (IRSA)
EKS_OIDC_ID=$(aws eks describe-cluster --name llmplatform-dev --query "cluster.identity.oidc.issuer" --output text | awk -F'/' '{print $NF}')

# Install the addon
aws eks create-addon \
  --cluster-name llmplatform-dev \
  --addon-name aws-ebs-csi-driver \
  --service-account-role-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/llmplatform-dev-ebs-csi-driver \
  --region us-west-2

# Update addon
aws eks update-addon \
  --cluster-name llmplatform-dev \
  --addon-name aws-ebs-csi-driver \
  --service-account-role-arn "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/llmplatform-dev-ebs-csi-driver" \
  --region us-west-2 \
  --resolve-conflicts OVERWRITE
```

Install the NVIDIA device plugin (required for GPU node scheduling):

```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.5/nvidia-device-plugin.yml
```

### 1.4 Configure kubectl

```bash
aws eks update-kubeconfig \
  --name llmplatform-dev \
  --region us-west-2

# Verify connectivity
kubectl get nodes
kubectl get namespaces
```

Expected namespaces: `platform`, `quant`, `finetune`, `eval`, `observability`, `llm-baseline`

---

## Phase 2 — Deploy Kubernetes Base (Kustomize)

### 2.1 Apply all base manifests

```bash
up 3 && cd k8s/

# Apply the full base (namespaces + all services except images won't resolve yet)
kubectl apply -k base/
```

### 2.2 Apply dev overlay (sets ECR image tags)

> **Note:** The manifests ship with AWS account ID `388691194728` hardcoded in base deployments, service accounts, and overlay kustomizations. If you are deploying to a **different** AWS account, replace it first:
>
> ```bash
> export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
> find k8s/ -name '*.yaml' | xargs sed -i "s/388691194728/${AWS_ACCOUNT_ID}/g"
> ```

```bash
cd k8s/overlays/dev

# Apply overlay (patches replicas, resources, image tags)
kubectl apply -k .
```

### 2.3 Verify namespaces and quotas

```bash
kubectl get resourcequotas --all-namespaces
```

Expected quotas:

| Namespace       | CPU Requests | Memory Requests | Max Pods |
| --------------- | ------------ | --------------- | -------- |
| `platform`      | 4            | 8Gi             | 20       |
| `quant`         | 8            | 16Gi            | 15       |
| `finetune`      | 4            | 8Gi             | 10       |
| `eval`          | 4            | 8Gi             | 10       |
| `observability` | 8            | 16Gi            | 30       |

---

## Phase 3 — Deploy the Observability Stack

### 3.1 Apply observability manifests

```bash
kubectl apply -f k8s/base/observability/
```

This deploys:

- **OTEL Collector** (contrib v0.95.0) — receives traces (4317 gRPC / 4318 HTTP), exports to Prometheus, Loki, Tempo
- **Prometheus** (v2.49.0) — metrics storage, scrapes `/metrics` from all pods
- **Loki** (v3.0.0) — log aggregation (tsdb/v13 schema)
- **Tempo** (v2.3.1) — distributed trace storage
- **Grafana** (v10.3.1) — dashboards, datasources pre-configured

### 3.2 Verify pods are running

```bash
kubectl get pods -n observability
```

Expected:

```
NAME                              READY   STATUS    RESTARTS
otel-collector-xxxxxxxxxx-xxxxx   1/1     Running   0
prometheus-xxxxxxxxxx-xxxxx       1/1     Running   0
loki-xxxxxxxxxx-xxxxx             1/1     Running   0
tempo-xxxxxxxxxx-xxxxx            1/1     Running   0
grafana-xxxxxxxxxx-xxxxx          1/1     Running   0
```

### 3.3 Access Grafana (port-forward)

```bash
kubectl port-forward -n observability svc/grafana 3000:3000 &
# Open http://localhost:3000 — default credentials: admin / admin
```

---

## Phase 4 — Deploy the Model Fleet (vLLM / Mistral-7B × 4 variants)

### 4.1 Create the HuggingFace token secret

```bash
export HF_TOKEN="hf_your-token-here"

kubectl create secret generic hf-token \
  --from-literal=HUGGING_FACE_HUB_TOKEN="$HF_TOKEN" \
  -n llm-baseline
```

> **Important:** Do NOT rely on the `hf-token-secret.yaml` template — it contains a `${HF_TOKEN}` placeholder that is not auto-substituted. Always create the secret via `kubectl create secret`.

> **Security tip:** In production, use Sealed Secrets or External Secrets Operator instead of `kubectl create secret`.

### 4.2 GPU nodes (SPOT)

GPU nodes are provisioned via Terraform with `capacity_type = "SPOT"` and `desired_size = 4`:

```bash
cd infra/envs/dev
terraform apply  # Provisions 4x g4dn.xlarge SPOT nodes

# Verify all 4 GPU nodes are Ready
kubectl get nodes -l nvidia.com/gpu.present=true
```

### 4.3 Deploy all 4 model variants

```bash
kubectl apply -k k8s/base/llm-baseline/
```

This creates 4 vLLM deployments with **pod anti-affinity** (one model per GPU node):

| Deployment | Model | Team | Key Config |
|-----------|-------|------|------------|
| `mistral-7b-awq` | TheBloke/Mistral-7B-Instruct-v0.2-AWQ | Quant | `--quantization awq`, max_len=4096 |
| `mistral-7b-fp16` | mistralai/Mistral-7B-Instruct-v0.2 | Platform (ref) | `--dtype half`, max_len=1024 |
| `mistral-7b-lora` | AWQ base + LoRA | Finetune | `--enable-lora`, max_loras=4 |
| `mistral-7b-judge` | TheBloke/Mistral-7B-Instruct-v0.2-AWQ | Eval | `--quantization awq`, max_len=4096 |

Team services route to their dedicated model via `VLLM_BASE_URL` in their ConfigMaps.

### 4.4 Wait for the model to load

```bash
# Watch in terminal
kubectl get pods -n llm-baseline -w

# This can take 3-5 minutes (model download + GPU load)
kubectl wait --for=condition=ready pod \
  -l app=mistral-7b-instruct-vllm \
  -n llm-baseline \
  --timeout=600s
```

### 4.5 Validate the baseline

```bash
# Run the golden checks script
./scripts/golden-checks.sh
```

Or manually:

```bash
# Port-forward to the vLLM service
kubectl port-forward -n llm-baseline svc/mistral-7b-baseline 8080:8000 &

# Check available models
curl http://localhost:8080/v1/models | python3 -m json.tool

# Send a test completion
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "TheBloke/Mistral-7B-Instruct-v0.2-AWQ",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "max_tokens": 50
  }' | python3 -m json.tool

# Check vLLM metrics
curl http://localhost:8080/metrics | head -30
```

---

## Phase 5 — Build & Deploy Application Services

### 5.1 Build and push Docker images

All service Dockerfiles use `services/` as the build context so they can
`COPY shared/` for the common library.

```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com"
export IMAGE_TAG=$(git rev-parse --short HEAD)

# Authenticate Docker to ECR
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Build and push all four services (context = services/)
for svc in gateway quant-api finetune-api eval-api; do
  echo "Building $svc..."
  docker build \
    -t "${ECR_REGISTRY}/llmplatform-dev/${svc}:${IMAGE_TAG}" \
    -t "${ECR_REGISTRY}/llmplatform-dev/${svc}:dev-latest" \
    -f "services/${svc}/Dockerfile" \
    services/

  docker push "${ECR_REGISTRY}/llmplatform-dev/${svc}:${IMAGE_TAG}"
  docker push "${ECR_REGISTRY}/llmplatform-dev/${svc}:dev-latest"
done
```

> **Important:** The build context is `services/` (not `services/<svc>/`) because each Dockerfile copies `shared/` for the common telemetry and model libraries.

### 5.2 Deploy with Kustomize dev overlay

```bash
cd k8s/overlays/dev
kubectl apply -k .
```

The dev overlay sets `newTag: dev-latest` for all 4 service images. Make sure your push step (5.1) tags images with `dev-latest`.

### 5.3 Verify all services

```bash
# Check rollout status
for svc in gateway quant-api finetune-api eval-api; do
  ns=$(kubectl get deploy -A -l app=$svc -o jsonpath='{.items[0].metadata.namespace}')
  echo "=== $svc ($ns) ==="
  kubectl rollout status deployment/$svc -n $ns --timeout=120s
done

# Check all pods across namespaces via the part-of label
kubectl get pods --all-namespaces -l app.kubernetes.io/part-of=llm-optimization-platform
```

Expected output (1 gateway, 2 each for team services):

```
NAMESPACE   NAME                            READY   STATUS
platform    gateway-xxxxxxxxxx-xxxxx        1/1     Running
quant       quant-api-xxxxxxxxxx-xxxxx      1/1     Running
quant       quant-api-xxxxxxxxxx-xxxxx      1/1     Running
finetune    finetune-api-xxxxxxxxxx-xxxxx   1/1     Running
finetune    finetune-api-xxxxxxxxxx-xxxxx   1/1     Running
eval        eval-api-xxxxxxxxxx-xxxxx       1/1     Running
eval        eval-api-xxxxxxxxxx-xxxxx       1/1     Running
```

> The `app.kubernetes.io/part-of` label propagates to pod templates via `includeTemplates: true` in the base kustomization.

### 5.4 Install Python dependencies (for local development)

```bash
# Shared library + any service
cd services
pip install -r shared/requirements.txt
pip install -r gateway/requirements.txt       # or whichever service
```

---

## Phase 6 — First End-to-End Request

### 6.1 Port-forward the gateway

```bash
kubectl port-forward -n platform svc/gateway 8000:8000 &
```

### 6.2 Health check

```bash
curl http://localhost:8000/health | python3 -m json.tool
```

### 6.3 Send a prediction request

```bash
# Quant team endpoint
curl -s -X POST http://localhost:8000/api/quant/predict \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: startup-test-001" \
  -d '{
    "prompt": "Explain quantization in one sentence.",
    "max_tokens": 50
  }' | python3 -m json.tool

# Finetune team (A/B routing: lora-v1 80% / lora-v2 20%)
curl -s -X POST http://localhost:8000/api/finetune/predict \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: startup-test-002" \
  -d '{
    "prompt": "Summarize the benefits of LoRA fine-tuning.",
    "max_tokens": 100
  }' | python3 -m json.tool

# Eval team
curl -s -X POST http://localhost:8000/api/eval/predict \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: startup-test-003" \
  -d '{
    "prompt": "Rate this response for coherence.",
    "max_tokens": 30
  }' | python3 -m json.tool
```

### 6.4 Verify observability

After sending requests, confirm telemetry is flowing:

```bash
# Check traces in Grafana → Explore → Tempo
# Check metrics in Grafana → Explore → Prometheus
#   Query: gateway_requests_total

# Or via Prometheus directly:
kubectl port-forward -n observability svc/prometheus 9090:9090 &
curl 'http://localhost:9090/api/v1/query?query=gateway_requests_total' | python3 -m json.tool
```

---

## Phase 7 — Grafana Plugin & Dashboard

### 7.1 Build the plugin

```bash
cd grafana-plugins/llm-platform-ops

npm install
npm run build        # Production webpack build
npm run package      # Creates llmplatform-ops-panel-1.0.0.zip
```

### 7.2 Install in Grafana

```bash
# Copy the built plugin to Grafana's plugin directory
kubectl cp dist/ observability/$(kubectl get pod -n observability -l app=grafana -o jsonpath='{.items[0].metadata.name}'):/var/lib/grafana/plugins/llmplatform-ops-panel/

# Restart Grafana to pick up the plugin
kubectl rollout restart deployment/grafana -n observability
```

### 7.3 Create dashboard

1. Open Grafana at `http://localhost:3000`
2. Go to **Dashboards → New → Add Panel**
3. Select **LLM Platform Ops** panel type
4. Configure the gateway URL (default: `http://gateway.platform.svc.cluster.local:8000`)

---

## Phase 8 — Data Engine & Test Harness

### 8.1 Generate promptsets

```python
from services.data_engine.generator import PromptsetGenerator

gen = PromptsetGenerator(seed=42)
gen.generate_promptset(
    scenario_id="canary-v1",
    dataset_id="general-qa",
    prompts=[
        {"text": "What is machine learning?", "category": "definition"},
        {"text": "Explain the transformer architecture in detail.", "category": "explanation"},
    ],
    output_dir="./output/promptsets"
)
# Output: promptset.jsonl + manifest.json with token counts and checksums
```

### 8.2 Run the test harness

```bash
python services/test-harness/harness.py \
  --promptset ./output/promptsets/promptset.jsonl \
  --gateway http://localhost:8000 \
  --team quant \
  --concurrency 10 \
  --run-id run-$(date +%Y%m%d-%H%M%S)
```

Output includes: total requests, pass/fail counts, pass rate %, average latency, and OTEL metrics (`lab_harness_requests_total`, `lab_harness_latency_ms`).

### 8.3 Run comparison scripts

```bash
# Quantized vs baseline comparison
./scripts/quant-comparison.sh

# Finetune A/B test
./scripts/finetune-ab-test.sh

# Autoscaling validation (load test → HPA scale-up → cooldown)
./scripts/validate-autoscaling.sh
```

---

## Phase 9 — CI/CD (GitHub Actions)

### 9.1 Required GitHub Secrets

Set these in your repository's **Settings → Secrets and variables → Actions**:

| Secret           | Value                        |
| ---------------- | ---------------------------- |
| `AWS_ACCOUNT_ID` | Your 12-digit AWS account ID |

The `github_oidc` Terraform module creates the OIDC provider and IAM role `llmplatform-github-actions` automatically.

### 9.2 Workflow triggers

| Workflow                 | Trigger                                       | What it does                              |
| ------------------------ | --------------------------------------------- | ----------------------------------------- |
| `ci-cd.yaml`             | Push to `main`/`develop` (services/k8s paths) | Lint → test → build → push → deploy       |
| `terraform.yaml`         | Push to `main` (infra paths) or manual        | fmt → plan → apply (or destroy)           |
| `rollback.yaml`          | Manual dispatch                               | Emergency rollback to previous deployment |
| `post-deploy-smoke.yaml` | After deploy                                  | Smoke tests against live endpoints        |

### 9.3 Branch strategy

- **`develop`** → auto-deploys to `dev` cluster (no approval)
- **`main`** → deploys to `prod` cluster (requires `production` environment approval in GitHub)

---

## Validation Scripts

| Script                            | Purpose                                           | Usage                               |
| --------------------------------- | ------------------------------------------------- | ----------------------------------- |
| `scripts/golden-checks.sh`        | vLLM health: rollout, `/v1/models`, chat, metrics | `./scripts/golden-checks.sh`        |
| `scripts/failure-demos.sh`        | Slow startup, quota rejection, SageMaker timeout  | `./scripts/failure-demos.sh`        |
| `scripts/quant-comparison.sh`     | Quantized vs baseline latency/quality             | `./scripts/quant-comparison.sh`     |
| `scripts/finetune-ab-test.sh`     | A/B routing validation                            | `./scripts/finetune-ab-test.sh`     |
| `scripts/validate-autoscaling.sh` | HPA scale-up/down under load                      | `./scripts/validate-autoscaling.sh` |

---

## Environment Variables Reference

### Gateway (ConfigMap `gateway-config`)

| Variable                      | Default                                                                      |
| ----------------------------- | ---------------------------------------------------------------------------- |
| `LOG_LEVEL`                   | `INFO`                                                                       |
| `AWS_REGION`                  | `us-west-2`                                                                  |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector.observability.svc.cluster.local:4317`                 |
| `OTEL_SERVICE_NAME`           | `gateway`                                                                    |
| `QUANT_SERVICE_URL`           | `http://quant-api.quant.svc.cluster.local`                                   |
| `FINETUNE_SERVICE_URL`        | `http://finetune-api.finetune.svc.cluster.local`                             |
| `EVAL_SERVICE_URL`            | `http://eval-api.eval.svc.cluster.local`                                     |
| `ROUTE_TABLE`                 | JSON — quant (30s), finetune (60s, A/B: lora-v1 80%/lora-v2 20%), eval (45s) |

### Team Services

| Variable                  | Default      | Used By                           |
| ------------------------- | ------------ | --------------------------------- |
| `SAGEMAKER_ENDPOINT_NAME` | `""` (empty) | quant-api, finetune-api, eval-api |
| `SAGEMAKER_TIMEOUT_MS`    | `30000`      | quant-api                         |
| `ENABLE_FALLBACK`         | `false`      | quant-api                         |
| `AB_ROUTING_ENABLED`      | `true`       | finetune-api                      |

> **Dev mode:** `SAGEMAKER_ENDPOINT_NAME` is set to `""` (empty) in the base ConfigMaps. When empty, the service lifespans skip SageMaker client initialization and health probes pass without requiring a live SageMaker endpoint. Set it to a real endpoint name (e.g., `quant-endpoint`) when SageMaker is provisioned.

### Shared Telemetry

| Variable                      | Default                                                      |
| ----------------------------- | ------------------------------------------------------------ |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector.observability.svc.cluster.local:4317` |
| `ENVIRONMENT`                 | `dev`                                                        |

---

## Service URLs & Ports

### In-Cluster DNS

| Service               | URL                                                         | Port |
| --------------------- | ----------------------------------------------------------- | ---- |
| Gateway               | `http://gateway.platform.svc.cluster.local`                 | 8000 |
| Quant API             | `http://quant-api.quant.svc.cluster.local`                  | 8000 |
| Finetune API          | `http://finetune-api.finetune.svc.cluster.local`            | 8000 |
| Eval API              | `http://eval-api.eval.svc.cluster.local`                    | 8000 |
| vLLM Baseline         | `http://mistral-7b-baseline.llm-baseline.svc.cluster.local` | 8000 |
| OTEL Collector (gRPC) | `http://otel-collector.observability.svc.cluster.local`     | 4317 |
| OTEL Collector (HTTP) | `http://otel-collector.observability.svc.cluster.local`     | 4318 |
| Prometheus            | `http://prometheus.observability.svc.cluster.local`         | 9090 |
| Grafana               | `http://grafana.observability.svc.cluster.local`            | 3000 |

### Local Port-Forwards (for development)

```bash
# Gateway
kubectl port-forward -n platform svc/gateway 8000:8000 &

# Grafana
kubectl port-forward -n observability svc/grafana 3000:3000 &

# Prometheus
kubectl port-forward -n observability svc/prometheus 9090:9090 &

# vLLM baseline
kubectl port-forward -n llm-baseline svc/mistral-7b-baseline 8080:8000 &
```

---

## Troubleshooting

### GPU nodes not scaling up

```bash
# Check if the GPU node group exists and has capacity
kubectl get nodes -l nvidia.com/gpu.present=true

# Check pending pods
kubectl get pods -n llm-baseline -o wide

# Check EKS node group capacity
aws eks describe-nodegroup \
  --cluster-name llmplatform-dev \
  --nodegroup-name gpu \
  --query 'nodegroup.scalingConfig'
```

If `desired_size` is `0`, scale it manually or install the Cluster Autoscaler to trigger scale-up on pending pods.

### vLLM CrashLoopBackOff — GPU memory

If vLLM crashes with `No available memory for the cache blocks`:

- **Root cause:** The model weights consume too much GPU VRAM for KV cache blocks
- **T4 (16GB):** Cannot run Mistral-7B at float16 (~14GB). Use AWQ 4-bit quantized model
- Add `--disable-frontend-multiprocessing` to vLLM args temporarily to see the real error (vLLM v0.6+ hides engine errors behind multi-process architecture)
- See [deployment-fixes.md](deployment-fixes.md) Fix #16 for full details

### OTEL Collector not receiving traces

```bash
# Check collector logs
kubectl logs -n observability -l app=otel-collector --tail=50

# Verify the endpoint is reachable from a service pod
kubectl exec -n platform deploy/gateway -- \
  curl -s otel-collector.observability.svc.cluster.local:4317
```

### SageMaker endpoint errors

```bash
# Check endpoint status
aws sagemaker describe-endpoint \
  --endpoint-name llmplatform-dev-quant-endpoint \
  --query 'EndpointStatus'

# Check IRSA annotation on service account
kubectl get sa quant-sa -n quant -o yaml | grep eks.amazonaws.com/role-arn
```

### Pod crashlooping

```bash
# Check logs
kubectl logs -n <namespace> deploy/<service-name> --tail=100

# Check events
kubectl describe pod -n <namespace> -l app=<service-name>

# Check resource quota usage
kubectl describe resourcequota -n <namespace>
```

### Image pull errors

```bash
# Verify ECR login
aws ecr get-login-password --region us-west-2 | \
  docker login --username AWS --password-stdin \
  "${AWS_ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com"

# Check if the image exists with the expected tag
aws ecr describe-images \
  --repository-name llmplatform-dev/gateway \
  --query 'imageDetails[*].imageTags'
```

Common causes:

- **`InvalidImageName`** — literal `ACCOUNT_ID` placeholder still in manifests. Run `grep -r ACCOUNT_ID k8s/` to check, then replace with your real account ID.
- **`ImagePullBackOff` with `not found`** — the image tag doesn't match. The dev overlay sets `newTag: dev-latest` via Kustomize, so images must be pushed with the `dev-latest` tag (not just `latest`).

### Service pods CrashLoopBackOff — import errors

If services crash with `ModuleNotFoundError: No module named 'shared'`:

- Ensure `ENV PYTHONPATH=/app` is set in the Dockerfile. Without it, Python can't resolve imports like `from shared.telemetry import setup_telemetry` when `WORKDIR` is `/app/<svc>/`.

If services crash with `ImportError` from `opentelemetry.*`:

- Check that `httpx` is listed in `services/shared/requirements.txt` (required by `opentelemetry-instrumentation-httpx`).
- The shared telemetry module relies on SDK-default W3C propagation — no explicit propagator packages needed.

### Health probe failures (startup 404 or 503)

If pods are `Running` but `0/1 Ready` and logs show `GET /startup` returning 404 or 503:

- **Gateway 404** — the gateway needs `/startup`, `/health`, and `/ready` endpoints in `main.py`.
- **Team services 503** — the `HealthChecker.startup_check()` calls `sagemaker_client.check_endpoint_status()`. If no SageMaker endpoint exists, it always returns `False`. Set `SAGEMAKER_ENDPOINT_NAME=""` in the ConfigMap so the lifespan passes `None` to `HealthChecker`, which then auto-transitions to `READY` state.

---

## Teardown

Two options depending on how long you'll be away.

### Option A — Pause nodes (keep cluster shell)

Scales all EC2 node groups to zero. The EKS control plane stays (~$0.10/hr) but all node, GPU, and pod costs stop immediately. Fastest way to resume — scale back up and re-apply manifests.

```bash
cd terraform

# Scale every node group to 0
terraform apply \
  -var="general_desired=0" -var="general_min=0" \
  -var="gpu_desired=0"     -var="gpu_min=0"
```

To resume next session:

```bash
# Restore node counts (adjust to your defaults)
terraform apply \
  -var="general_desired=2" -var="general_min=1" \
  -var="gpu_desired=1"     -var="gpu_min=0"

# Wait for nodes
kubectl get nodes -w

# Re-apply workloads (pods were evicted when nodes disappeared)
kubectl apply -k k8s/overlays/dev/
kubectl apply -k k8s/base/llm-baseline/
kubectl apply -k k8s/base/observability/
```

### Option B — Full teardown (zero cost, recommended overnight)

Destroys everything — EKS cluster, VPC, node groups, IAM roles, ECR repos. Zero AWS spend. All manifests and code are in Git, so nothing is lost. Full rebuild takes ~15–20 minutes.

```bash
# 1. Delete K8s workloads first (releases ELBs/PVCs that block Terraform)
kubectl delete -k k8s/overlays/dev/
kubectl delete -k k8s/base/llm-baseline/
kubectl delete namespace observability --timeout=60s

# 2. Destroy all Terraform infrastructure
cd terraform
terraform destroy
```

To rebuild from scratch, follow the guide from [Phase 1](#phase-1--provision-infrastructure-terraform).

---

## Design Documents

| #   | Document                                            | Description                                          |
| --- | --------------------------------------------------- | ---------------------------------------------------- |
| 01  | [Terraform IaC](design-01-infrastructure.md)        | VPC, EKS, ECR, IRSA, remote state                    |
| 02  | [Kubernetes Orchestration](design-02-kubernetes.md) | 6 namespaces, probes, quotas, Kustomize              |
| 03  | [Observability Stack](design-03-observability.md)   | OTEL Collector → Prometheus / Loki / Tempo → Grafana |
| 04  | [SageMaker Integration](design-04-sagemaker.md)     | Team wrappers, gateway routing, A/B variants         |
| 05  | [GitHub Actions CI/CD](design-05-cicd.md)           | OIDC auth, build/push/deploy pipelines               |
| 06  | [Operations Dashboard](design-06-dashboard.md)      | Grafana plugin, gateway ops API                      |
| 07  | [Acceptance Checklist](design-07-checklist.md)      | Done-means-done criteria, verification commands      |
| 08  | [OTel Attribute Schema](design-08-otel-schema.md)   | Canonical telemetry attributes, cardinality safety   |
| 09  | [Data Engine](design-09-data-engine.md)             | Promptsets, test harness, controlled failures        |
| 10  | [Baseline Model](design-10-models.md)               | vLLM deployment, Mistral-7B for comparisons          |
