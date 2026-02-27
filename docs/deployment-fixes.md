# Deployment Fixes

Technical reference for issues encountered and resolved during the initial deployment of the LLM Optimization Platform on EKS.

**Cluster:** `llmplatform-dev` · **Region:** `us-west-2` · **EKS Version:** 1.29
**Date:** 2026-02-25

---

## 1. EBS CSI Driver Missing

**Symptom:** All PersistentVolumeClaims remained in `Pending` state indefinitely. Pods referencing those PVCs could not be scheduled.

**Root Cause:** The cluster had no EBS CSI driver addon installed. The default `gp2` StorageClass uses `volumeBindingMode: WaitForFirstConsumer` with the legacy in-tree provisioner (`kubernetes.io/aws-ebs`), which does not function correctly on EKS 1.29 without the CSI driver.

**Fix:**

1. Created an IAM role with IRSA trust for the EBS CSI controller service account:

```bash
# Trust policy for OIDC federation
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::388691194728:oidc-provider/oidc.eks.us-west-2.amazonaws.com/id/<OIDC_ID>"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "<OIDC_ISSUER>:aud": "sts.amazonaws.com",
        "<OIDC_ISSUER>:sub": "system:serviceaccount:kube-system:ebs-csi-controller-sa"
      }
    }
  }]
}

aws iam create-role \
  --role-name llmplatform-dev-ebs-csi-driver \
  --assume-role-policy-document file://ebs-csi-trust-policy.json

aws iam attach-role-policy \
  --role-name llmplatform-dev-ebs-csi-driver \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy
```

2. Installed the addon:

```bash
aws eks create-addon \
  --cluster-name llmplatform-dev \
  --addon-name aws-ebs-csi-driver \
  --service-account-role-arn arn:aws:iam::388691194728:role/llmplatform-dev-ebs-csi-driver \
  --region us-west-2
```

**Addon version installed:** `v1.56.0-eksbuild.1`

---

## 2. PVC StorageClass `gp3` Does Not Exist

**Symptom:** PVCs stuck in `Pending`. `kubectl describe pvc` showed no provisioning events.

**Root Cause:** All 5 PVC definitions specified `storageClassName: gp3`, but the cluster only has `gp2 (default)`. No `gp3` StorageClass was ever created.

**Affected PVCs:**

| PVC Name          | Namespace     | Size  |
| ----------------- | ------------- | ----- |
| `prometheus-data` | observability | 50Gi  |
| `loki-data`       | observability | 50Gi  |
| `tempo-data`      | observability | 20Gi  |
| `hf-cache-pvc`    | llm-baseline  | 50Gi  |
| `hf-cache`        | llm-baseline  | 200Gi |

**Fix:** Changed `storageClassName: gp3` → `storageClassName: gp2` in all 5 source files, then deleted and recreated the PVCs (storageClassName is immutable on existing PVCs):

**Files modified:**

- `k8s/base/observability/prometheus-deployment.yaml`
- `k8s/base/observability/loki-deployment.yaml`
- `k8s/base/observability/tempo-deployment.yaml`
- `k8s/base/llm-baseline/pvc.yaml`
- `k8s/base/llm-baseline/hf-cache-pvc.yaml`

```bash
# Delete old PVCs
kubectl delete pvc prometheus-data loki-data tempo-data -n observability
kubectl delete pvc hf-cache-pvc -n llm-baseline

# Re-apply to recreate with gp2
kubectl apply -f k8s/base/observability/prometheus-deployment.yaml
kubectl apply -f k8s/base/observability/loki-deployment.yaml
kubectl apply -f k8s/base/observability/tempo-deployment.yaml
kubectl apply -k k8s/overlays/dev/
```

---

## 3. Prometheus — Permission Denied on Data Volume

**Symptom:** Prometheus pod in `CrashLoopBackOff` with:

```
open /prometheus/queries.active: permission denied
panic: Unable to create mmap-ed active query log
```

**Root Cause:** The EBS volume is mounted as root-owned by default. The Prometheus container runs as user `65534` (nobody) and cannot write to `/prometheus`.

**Fix:** Added `securityContext` with `fsGroup: 65534` to the pod spec in `k8s/base/observability/prometheus-deployment.yaml`:

```yaml
spec:
  template:
    spec:
      securityContext:
        fsGroup: 65534
        runAsUser: 65534
        runAsNonRoot: true
      containers:
        - name: prometheus
          # ...
```

`fsGroup` causes Kubernetes to chown the mounted volume to GID 65534, allowing the Prometheus process to write.

---

## 4. Loki — Deprecated Config Field (`enforce_metric_name`)

**Symptom:** Loki pod in `CrashLoopBackOff` with:

```
failed parsing config: /etc/loki/config.yaml: yaml: unmarshal errors:
  line 28: field enforce_metric_name not found in type validation.plain
```

**Root Cause:** The `limits_config.enforce_metric_name` field was removed in Loki v3.0.0 but was still present in the ConfigMap.

**Fix:** Removed the deprecated field from the `loki-config` ConfigMap in `k8s/base/observability/loki-deployment.yaml`:

```yaml
# Before
limits_config:
  enforce_metric_name: false    # ← removed
  reject_old_samples: true
  reject_old_samples_max_age: 168h

# After
limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h
```

---

## 5. Loki — Permission Denied on Data Volume

**Symptom:** After fixing the config, Loki crashed with:

```
mkdir /loki/rules: permission denied
error initialising module: ruler-storage
```

**Root Cause:** Same as Prometheus — the EBS volume mounts as root-owned but Loki runs as UID 10001.

**Fix:** Added `securityContext` with `fsGroup: 10001` to the pod spec in `k8s/base/observability/loki-deployment.yaml`:

```yaml
spec:
  template:
    spec:
      securityContext:
        fsGroup: 10001
        runAsUser: 10001
        runAsNonRoot: true
      containers:
        - name: loki
          # ...
```

---

## 6. Grafana — Missing ConfigMaps and Secret

**Symptom:** Grafana pod stuck in `ContainerCreating` with volume mount failures:

```
MountVolume.SetUp failed for volume "dashboards" : configmap "grafana-dashboards" not found
MountVolume.SetUp failed for volume "dashboards-provider" : configmap "grafana-dashboards-provider" not found
```

**Root Cause:** The `grafana-deployment.yaml` references three resources that were never defined in any manifest:

- ConfigMap `grafana-dashboards-provider` — dashboard provisioning config
- ConfigMap `grafana-dashboards` — JSON dashboard definitions
- Secret `grafana-secrets` — admin password

**Fix:** Created all three resources in the `observability` namespace:

**`grafana-dashboards-provider`** — tells Grafana where to find dashboard JSON files:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards-provider
  namespace: observability
data:
  dashboards.yaml: |
    apiVersion: 1
    providers:
      - name: 'default'
        orgId: 1
        folder: ''
        type: file
        disableDeletion: false
        editable: true
        options:
          path: /var/lib/grafana/dashboards
```

**`grafana-dashboards`** — starter dashboard with LLM platform panels (request rate, p95 latency, active inference requests, token throughput).

**`grafana-secrets`** — contains `admin-password` key (set to `admin` for dev).

---

## 7. OTEL Collector — Loki Exporter Invalid Config

**Symptom:** Both OTEL Collector pods in `CrashLoopBackOff` with:

```
'loki' exporter: '' has invalid keys: labels
```

**Root Cause:** The Loki exporter config used a `labels.attributes` block that is not valid in the OpenTelemetry Collector Contrib Loki exporter. The correct field is `default_labels_enabled`.

**Fix:** Updated the Loki exporter section in `k8s/base/observability/otel-collector-config.yaml`:

```yaml
# Before
exporters:
  loki:
    endpoint: "http://loki.observability.svc:3100/loki/api/v1/push"
    labels:
      attributes:
        - service.name
        - service.namespace

# After
exporters:
  loki:
    endpoint: "http://loki.observability.svc:3100/loki/api/v1/push"
    default_labels_enabled:
      exporter: true
      job: true
```

---

## 8. ServiceMonitor CRD Missing

**Symptom:** `kubectl apply -k k8s/base/llm-baseline/` failed with:

```
no matches for kind "ServiceMonitor" in version "monitoring.coreos.com/v1"
ensure CRDs are installed first
```

**Root Cause:** The `servicemonitor.yaml` resource references the `ServiceMonitor` CRD from Prometheus Operator, which is not installed — we run standalone Prometheus.

**Fix:** Removed `servicemonitor.yaml` from `k8s/base/llm-baseline/kustomization.yaml`:

```yaml
# Before
resources:
  - hf-token-secret.yaml
  - hf-cache-pvc.yaml
  - vllm-deployment.yaml
  - vllm-service.yaml
  - servicemonitor.yaml    # ← removed

# After
resources:
  - hf-token-secret.yaml
  - hf-cache-pvc.yaml
  - vllm-deployment.yaml
  - vllm-service.yaml
```

The file remains in the repo at `k8s/base/llm-baseline/servicemonitor.yaml` for use if Prometheus Operator is added later.

---

## 9. GPU Node Group — Wrong AMI Type

**Symptom:** vLLM pod stuck in `Pending` with `FailedScheduling` even after the GPU node joined the cluster. The NVIDIA device plugin reported:

```
Detected non-NVML platform: could not load NVML library:
  libnvidia-ml.so.1: cannot open shared object file: No such file or directory
Incompatible platform detected
If this is a GPU node, did you configure the NVIDIA Container Toolkit?
```

The GPU node showed no `nvidia.com/gpu` in its allocatable resources.

**Root Cause:** The EKS GPU node group was created with `ami_type: AL2_x86_64` (standard AMI) instead of `AL2_x86_64_GPU` (GPU AMI with pre-installed NVIDIA drivers and Container Toolkit). The Terraform EKS module had no `ami_type` field, so AWS defaulted to the standard AMI.

**Fix:**

1. Added `ami_type` field to the `node_groups` variable type in both the EKS module and env-level variables:

```terraform
# infra/modules/eks/variables.tf & infra/envs/dev/variables.tf
variable "node_groups" {
  type = map(object({
    instance_types = list(string)
    disk_size      = number
    desired_size   = number
    min_size       = number
    max_size       = number
    ami_type       = optional(string, "AL2_x86_64")  # ← added
    labels         = map(string)
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
}
```

2. Set `ami_type` in the EKS module resource:

```terraform
# infra/modules/eks/main.tf
resource "aws_eks_node_group" "main" {
  # ...
  instance_types  = each.value.instance_types
  ami_type        = each.value.ami_type          # ← added
  disk_size       = each.value.disk_size
  # ...
}
```

3. Set `ami_type = "AL2_x86_64_GPU"` for the gpu node group in tfvars:

```terraform
# infra/envs/dev/terraform.tfvars
gpu = {
  instance_types = ["g4dn.xlarge"]
  disk_size      = 100
  desired_size   = 0
  min_size       = 0
  max_size       = 2
  ami_type       = "AL2_x86_64_GPU"    # ← added
  labels = { ... }
  taints = [ ... ]
}
```

4. Applied with targeted replace (ami_type is immutable — forces node group recreation):

```bash
terraform apply -target='module.eks.aws_eks_node_group.main["gpu"]' -auto-approve
```

**Files modified:**

- `infra/modules/eks/variables.tf`
- `infra/modules/eks/main.tf`
- `infra/envs/dev/variables.tf`
- `infra/envs/dev/terraform.tfvars`

---

## 10. NVIDIA Device Plugin Not Installed

**Symptom:** GPU node had no `nvidia.com/gpu` resource advertised even with the correct AMI (before fix #9 was identified).

**Root Cause:** The NVIDIA k8s device plugin DaemonSet was never deployed to the cluster. It is required to expose GPU resources to the Kubernetes scheduler.

**Fix:** Installed the NVIDIA device plugin DaemonSet:

```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.5/nvidia-device-plugin.yml
```

This creates a DaemonSet that runs on all nodes and advertises `nvidia.com/gpu` resources for nodes with NVIDIA GPUs detected.

---

## 11. vLLM Resource Requests Exceed Node Capacity

**Symptom:** vLLM pod stuck in `Pending` with `Insufficient cpu` and `Insufficient memory` on the GPU node.

**Root Cause:** The vLLM deployment requested `cpu: 4` / `memory: 16Gi` but a `g4dn.xlarge` only has ~3.9 CPU / ~15Gi allocatable (after kubelet and system reservations).

**Fix:** Lowered resource requests/limits in `k8s/base/llm-baseline/vllm-deployment.yaml`:

```yaml
# Before
resources:
  limits:
    nvidia.com/gpu: "1"
    cpu: "8"
    memory: "32Gi"
  requests:
    nvidia.com/gpu: "1"
    cpu: "4"
    memory: "16Gi"

# After
resources:
  limits:
    nvidia.com/gpu: "1"
    cpu: "3"
    memory: "14Gi"
  requests:
    nvidia.com/gpu: "1"
    cpu: "2"
    memory: "12Gi"
```

**File modified:** `k8s/base/llm-baseline/vllm-deployment.yaml`

---

## 12. Insufficient Node Resources for Observability Pods

**Symptom:** All observability pods stuck in `Pending` with `FailedScheduling` — insufficient CPU/memory.

**Root Cause:** The general node group only had 2x `t3.medium` nodes (2 vCPU / 4Gi each), which couldn't fit the observability stack alongside system pods.

**Fix:** Scaled the general node group from 2 to 4 nodes:

```bash
aws eks update-nodegroup-config \
  --cluster-name llmplatform-dev \
  --nodegroup-name llmplatform-dev-general \
  --scaling-config minSize=1,maxSize=4,desiredSize=4 \
  --region us-west-2
```

---

## 13. Kustomize — ConfigMapGenerator Merge Error

**Symptom:** `kubectl apply -k k8s/overlays/dev/` failed with error about `gateway-config` ConfigMap not existing for strategic merge.

**Root Cause:** The overlay used `configMapGenerator` to merge into a base ConfigMap, but the base ConfigMap was a plain resource — not generated by kustomize.

**Fix:** Replaced `configMapGenerator` with an inline strategic merge patch in `k8s/overlays/dev/kustomization.yaml`:

```yaml
patches:
  - patch: |
      apiVersion: v1
      kind: ConfigMap
      metadata:
        name: gateway-config
        namespace: platform
      data:
        LOG_LEVEL: "DEBUG"
```

---

## 14. Kustomize — Deprecated `commonLabels`

**Symptom:** Warning about deprecated `commonLabels` field in kustomization files.

**Root Cause:** `commonLabels` was deprecated in favor of `labels` in newer kustomize versions.

**Fix:** Migrated both base and overlay kustomization files from `commonLabels` to `labels` with `pairs` syntax:

```yaml
# Before
commonLabels:
  app.kubernetes.io/part-of: llm-optimization-platform

# After
labels:
  - pairs:
      app.kubernetes.io/part-of: llm-optimization-platform
```

**Note:** This change altered selectors on existing deployments, making them immutable. Required deleting all 5 deployments before re-applying.

---

## 15. Immutable Selector Error After Label Migration

**Symptom:** `kubectl apply -k` failed with `spec.selector: Invalid value... field is immutable`.

**Root Cause:** Switching from `commonLabels` to `labels` changed the selector labels on existing deployments, which Kubernetes does not allow.

**Fix:** Deleted all existing deployments, then re-applied:

```bash
kubectl delete deployment gateway -n platform
kubectl delete deployment quant-api -n quant
kubectl delete deployment finetune-api -n finetune
kubectl delete deployment eval-api -n eval
kubectl delete deployment vllm-baseline -n llm-baseline
kubectl apply -k k8s/overlays/dev/
```

---

## Final State

All observability pods running:

```
NAME                              READY   STATUS    AGE
grafana-66596698bf-vm45b          1/1     Running   114s
loki-77b88fcc7c-xdtf7             1/1     Running   36s
otel-collector-5b68dfd695-82ss7   1/1     Running   18m
otel-collector-5b68dfd695-g5tzl   1/1     Running   18m
prometheus-657547fc85-cpp8n       1/1     Running   36s
tempo-5f5fbdcc86-dh2hc            1/1     Running   5m
```

PVCs all bound via `gp2` StorageClass:

```
NAME              STATUS   CAPACITY   STORAGECLASS
loki-data         Bound    50Gi       gp2
prometheus-data   Bound    50Gi       gp2
tempo-data        Bound    20Gi       gp2
```

vLLM baseline pod running on GPU node (`g4dn.xlarge`, `AL2_x86_64_GPU` AMI) with 1x NVIDIA T4 GPU, serving `TheBloke/Mistral-7B-Instruct-v0.2-AWQ` via AWQ 4-bit quantization:

```
NAME                                        READY   STATUS    AGE
mistral-7b-instruct-vllm-76c4cb45b8-8wdr9   1/1     Running   4m

$ curl localhost:8000/v1/models | jq '.data[0].id'
"TheBloke/Mistral-7B-Instruct-v0.2-AWQ"
```

All 4 application services running:

```
NAMESPACE   NAME                            READY   STATUS
platform    gateway-5bcfd5d67c-bvxpt        1/1     Running
quant       quant-api-674874d4b-bz82x       1/1     Running
finetune    finetune-api-65ffbc86c7-rlfhc   1/1     Running
eval        eval-api-cc87df6bf-4t4hk        1/1     Running
```

---

## 16. vLLM GPU Memory Exhaustion — Mistral-7B fp16 on T4

**Symptom:** vLLM pod in `CrashLoopBackOff`. Logs showed:

```
ValueError: No available memory for the cache blocks.
Try increasing `gpu_memory_utilization` when initializing the engine.
```

Later, after reducing `max-model-len` to 2048 and raising `gpu-memory-utilization` to 0.95:

```
ValueError: The model's max seq len (2048) is larger than the maximum number of
tokens that can be stored in KV cache (1936).
```

**Root Cause:** Mistral-7B-Instruct-v0.2 at float16 requires ~14GB for model weights alone. The NVIDIA T4 has 16GB VRAM — leaving <2GB for KV cache, which is insufficient for any meaningful sequence length.

**Fix:** Switched to the AWQ 4-bit quantized variant of the same model:

```yaml
# Before (fp16 — 14GB weights, no room for KV cache)
args:
  - "--model"
  - "mistralai/Mistral-7B-Instruct-v0.2"
  - "--dtype"
  - "half"

# After (AWQ 4-bit — ~4GB weights, ~12GB available for KV cache)
args:
  - "--model"
  - "TheBloke/Mistral-7B-Instruct-v0.2-AWQ"
  - "--quantization"
  - "awq"
  - "--dtype"
  - "half"
  - "--max-model-len"
  - "4096"
  - "--gpu-memory-utilization"
  - "0.90"
```

Also set deployment strategy to `Recreate` (single GPU prevents rolling updates).

**Additional fix — Debugging invisible errors:** vLLM v0.6.6 uses multi-process architecture by default. Engine crashes were hidden behind `RuntimeError: Engine process failed to start`. Adding `--disable-frontend-multiprocessing` surfaced the actual `ValueError`. This flag was removed after the fix was confirmed.

**Verification:**

```
$ kubectl get pods -n llm-baseline
NAME                                        READY   STATUS    AGE
mistral-7b-instruct-vllm-76c4cb45b8-8wdr9   1/1     Running   4m

$ curl localhost:8000/v1/chat/completions -d '{
    "model": "TheBloke/Mistral-7B-Instruct-v0.2-AWQ",
    "messages": [{"role": "user", "content": "What is the capital of France?"}],
    "max_tokens": 50
  }'
# Response: "The capital city of France is Paris."
```

**File:** `k8s/base/llm-baseline/vllm-deployment.yaml`

---

## 17. Stale Duplicate Resources in llm-baseline/

**Symptom:** Directory contained duplicate/conflicting files that were never referenced by `kustomization.yaml` but caused confusion and would break `kubectl apply -f` (non-Kustomize) workflows:

| Stale File        | Conflicts With         | Issue                                                             |
| ----------------- | ---------------------- | ----------------------------------------------------------------- |
| `deployment.yaml` | `vllm-deployment.yaml` | Wrong image (`:latest`), wrong model (fp16), wrong secret key ref |
| `service.yaml`    | `vllm-service.yaml`    | Selector `app: vllm-baseline` matches no pods                     |
| `pvc.yaml`        | `hf-cache-pvc.yaml`    | Separate 50Gi PVC named `hf-cache-pvc`, unused by deployment      |

Additionally, the live cluster had a stale `vllm-baseline` Service (from `service.yaml` applied in earlier phases) with a selector that matched no pods.

**Root Cause:** The initial implementation generated two naming conventions — `vllm-baseline` vs `mistral-7b-instruct-vllm` — across deployments, services, and PVCs. Only the `mistral-7b-*` / `vllm-deployment.yaml` set was kept in `kustomization.yaml`.

**Fix:**

1. Removed stale files from the repository:
   - `k8s/base/llm-baseline/deployment.yaml`
   - `k8s/base/llm-baseline/service.yaml`
   - `k8s/base/llm-baseline/pvc.yaml`

2. Deleted stale Service from the live cluster:

   ```bash
   kubectl delete svc vllm-baseline -n llm-baseline
   ```

3. Updated `golden-checks.sh` to use the correct model name (`TheBloke/Mistral-7B-Instruct-v0.2-AWQ`).

4. Updated `hf-token-secret.yaml` to document that the secret must be created via `kubectl create secret` (the `${HF_TOKEN}` placeholder is not auto-substituted).

**Files removed:** `deployment.yaml`, `service.yaml`, `pvc.yaml`
**Files modified:** `scripts/golden-checks.sh`, `k8s/base/llm-baseline/hf-token-secret.yaml`

---

## 18. Base Kustomization — Broken References to Deleted Files

**Symptom:** `kubectl apply -k k8s/overlays/dev/` failed with:

```
accumulating resources: accumulation err='accumulating resources from 'llm-baseline/deployment.yaml':
  evalsymlink failure on '/home/.../k8s/base/llm-baseline/deployment.yaml': lstat ... no such file or directory
```

**Root Cause:** Fix #17 deleted `deployment.yaml`, `service.yaml`, and `pvc.yaml` from `k8s/base/llm-baseline/`, but `k8s/base/kustomization.yaml` still listed them as resources on lines 36–38.

**Fix:** Removed the three stale resource references from `k8s/base/kustomization.yaml` and added comments explaining that llm-baseline has its own `kustomization.yaml` and should be applied separately:

```yaml
# Before
resources:
  # ...namespaces, gateway, quant-api, finetune-api, eval-api...
  - llm-baseline/deployment.yaml
  - llm-baseline/service.yaml
  - llm-baseline/pvc.yaml

# After
resources:
  # ...namespaces, gateway, quant-api, finetune-api, eval-api...
  # llm-baseline has its own kustomization.yaml — apply separately:
  #   kubectl apply -k k8s/base/llm-baseline/
```

**File modified:** `k8s/base/kustomization.yaml`

---

## 19. InvalidImageName — Literal `ACCOUNT_ID` Placeholder

**Symptom:** All 4 application service pods stuck in `InvalidImageName`:

```
Failed to apply default image tag
  "ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev/gateway:latest":
  couldn't parse image name: repository name must be lowercase
```

**Root Cause:** All base deployment manifests and service account IRSA annotations used the literal string `ACCOUNT_ID` instead of the real AWS account ID `388691194728`.

**Affected files (11 total):**

| File Type            | Files                                                                    |
| -------------------- | ------------------------------------------------------------------------ |
| Base deployments (4) | `k8s/base/{gateway,quant-api,finetune-api,eval-api}/deployment.yaml`     |
| Service accounts (4) | `k8s/base/{gateway,quant-api,finetune-api,eval-api}/serviceaccount.yaml` |
| Overlay images (2)   | `k8s/overlays/{staging,prod}/kustomization.yaml`                         |
| Ingress patch (1)    | `k8s/overlays/dev/patches/ingress-dev.yaml`                              |

**Fix:**

```bash
sed -i 's/ACCOUNT_ID/388691194728/g' \
  k8s/base/*/deployment.yaml \
  k8s/base/*/serviceaccount.yaml \
  k8s/overlays/dev/patches/ingress-dev.yaml \
  k8s/overlays/staging/kustomization.yaml \
  k8s/overlays/prod/kustomization.yaml
```

---

## 20. ImagePullBackOff — Tag Mismatch (`latest` vs `dev-latest`)

**Symptom:** After fixing the account ID, quant-api, finetune-api, and eval-api pods showed `ImagePullBackOff`:

```
Failed to pull image "...llmplatform-dev/finetune-api:dev-latest":
  ...llmplatform-dev/finetune-api:dev-latest: not found
```

**Root Cause:** Docker images were built and pushed with the tag `:latest`, but the dev overlay `k8s/overlays/dev/kustomization.yaml` uses Kustomize `images:` to override the tag to `:dev-latest`:

```yaml
images:
  - name: 388691194728.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev/gateway
    newTag: dev-latest
```

**Fix:** Tagged and pushed all 4 images with the `dev-latest` tag:

```bash
ECR=388691194728.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev
for svc in gateway quant-api finetune-api eval-api; do
  docker tag $ECR/$svc:latest $ECR/$svc:dev-latest
  docker push $ECR/$svc:dev-latest
done
```

---

## 21. Broken Dockerfiles — `COPY ../shared` Not Allowed

**Symptom:** Docker builds for quant-api, finetune-api, and eval-api failed because `COPY ../shared /app/shared` attempted to copy from outside the build context.

**Root Cause:** The three service Dockerfiles used `COPY ../shared /app/shared`, but Docker prohibits copying files from outside the build context. The gateway Dockerfile had already been fixed to use `services/` as the build context.

**Fix:** Rewrote all 3 Dockerfiles to match the gateway pattern — using `services/` as the Docker build context:

```dockerfile
# Before (built from services/<svc>/ context — can't reach ../shared)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ../shared /app/shared
COPY . /app

# After (built from services/ context)
COPY shared/requirements.txt /app/shared/requirements.txt
RUN pip install --no-cache-dir -r /app/shared/requirements.txt
COPY <svc>/requirements.txt /app/<svc>/requirements.txt
RUN pip install --no-cache-dir -r /app/<svc>/requirements.txt
COPY shared/ /app/shared/
COPY <svc>/ /app/<svc>/
WORKDIR /app/<svc>
```

Build command uses `services/` as context:

```bash
docker build -t $ECR/$svc:dev-latest -f $svc/Dockerfile .
# Run from within services/ directory
```

**Files modified:** `services/quant-api/Dockerfile`, `services/finetune-api/Dockerfile`, `services/eval-api/Dockerfile`

---

## 22. ModuleNotFoundError: `shared` — Missing PYTHONPATH

**Symptom:** All 4 service pods crashed on startup with:

```
ModuleNotFoundError: No module named 'shared'
```

**Root Cause:** The Dockerfile sets `WORKDIR /app/gateway` (or `/app/quant-api`, etc.) before running uvicorn. When Python tries `from shared.telemetry import setup_telemetry`, the `shared` package is at `/app/shared/`, which is not the current working directory and not on `sys.path`.

**Fix:** Added `ENV PYTHONPATH=/app` to all 4 Dockerfiles so Python can resolve `shared.*` imports from any working directory:

```dockerfile
WORKDIR /app/gateway

ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Files modified:** `services/gateway/Dockerfile`, `services/quant-api/Dockerfile`, `services/finetune-api/Dockerfile`, `services/eval-api/Dockerfile`

---

## 23. OpenTelemetry Import Errors in shared/telemetry.py

**Symptom:** Two different import errors across services:

Gateway + eval-api:

```
ImportError: cannot import name 'TraceContextTextMapPropagator'
  from 'opentelemetry.trace.propagation'
```

Quant-api + finetune-api:

```
ModuleNotFoundError: No module named 'httpx'
```

**Root Cause:** Two bugs in `services/shared/telemetry.py`:

1. **Wrong import path** — `TraceContextTextMapPropagator` was imported from `opentelemetry.trace.propagation` but that module doesn't export it. The correct path would be `opentelemetry.propagators.tracecontext`, which requires the separate `opentelemetry-propagator-tracecontext` package — but W3C propagation is already auto-configured by the SDK, making the explicit setup unnecessary.

2. **Missing transitive dependency** — `opentelemetry-instrumentation-httpx` requires `httpx` at runtime, but `httpx` wasn't listed in `services/shared/requirements.txt`. (Gateway had it separately; the other services didn't.)

**Fix:**

1. Removed explicit W3C propagator setup from `services/shared/telemetry.py` (the OpenTelemetry SDK auto-configures W3C Trace Context + Baggage propagation by default):

```python
# Removed these imports:
# from opentelemetry.propagate import set_global_textmap
# from opentelemetry.propagators.composite import CompositePropagator
# from opentelemetry.trace.propagation import TraceContextTextMapPropagator
# from opentelemetry.baggage.propagation import W3CBaggagePropagator

# Removed this block:
# set_global_textmap(CompositePropagator([
#     TraceContextTextMapPropagator(),
#     W3CBaggagePropagator()
# ]))
```

2. Added `httpx>=0.24,<1` to `services/shared/requirements.txt`.

**Files modified:** `services/shared/telemetry.py`, `services/shared/requirements.txt`

---

## 24. Health Probe Failures — Gateway + SageMaker Dependency

**Symptom:** After fixing all import errors, pods were `Running` but `0/1 Ready`. Startup probes returned:

- Gateway: `GET /startup` → **404 Not Found** (endpoint doesn't exist)
- Quant/finetune/eval: `GET /startup` → **503 Service Unavailable**

The deployment's `startupProbe` (30 failures × 5s = 150s) would eventually kill the pods, causing `CrashLoopBackOff`.

**Root Cause:** Two separate issues:

1. **Gateway had no health endpoints.** Its `main.py` only defined the `/api/{team}/predict` route — no `/startup`, `/health`, or `/ready` handlers. All other services had them via `shared.health.HealthChecker`.

2. **HealthChecker.startup_check() required SageMaker.** The startup check called `sagemaker_client.check_endpoint_status()` which calls `describe_endpoint()`. In dev, no SageMaker endpoints exist (`quant-endpoint`, `finetune-endpoint`, `eval-endpoint` are placeholder names), so the check always returned `False`.

**Fix:**

1. Added `/startup`, `/health`, and `/ready` endpoints to `services/gateway/main.py`:

```python
@app.get("/startup")
async def startup():
    return {"status": "started", "service": "gateway"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "gateway"}

@app.get("/ready")
async def ready():
    return {"status": "ready", "service": "gateway"}
```

2. Made `HealthChecker` handle a `None` SageMaker client — when no client is provided, startup/readiness checks pass based on state alone:

```python
# services/shared/health.py
async def startup_check(self) -> bool:
    if self.state == ServiceState.STARTING:
        if self.sagemaker_client is None:
            self.state = ServiceState.READY
            return True
        # ...existing SageMaker check...

async def readiness_check(self) -> bool:
    if self.sagemaker_client is None:
        return self.state == ServiceState.READY
    # ...existing SageMaker check...
```

3. Made all 3 team service lifespans pass `None` when `SAGEMAKER_ENDPOINT_NAME` is empty:

```python
# services/{quant,finetune,eval}-api/main.py
endpoint_name = os.getenv("SAGEMAKER_ENDPOINT_NAME", "")
if endpoint_name:
    app.state.sagemaker = SageMakerClient(endpoint_name=endpoint_name, ...)
else:
    app.state.sagemaker = None
app.state.health = HealthChecker(app.state.sagemaker)
```

4. Cleared `SAGEMAKER_ENDPOINT_NAME` in the base ConfigMaps (set to empty string) so dev services start without SageMaker:

```yaml
# k8s/base/{quant-api,finetune-api,eval-api}/configmap.yaml
SAGEMAKER_ENDPOINT_NAME: "" # was "quant-endpoint" / "finetune-endpoint" / "eval-endpoint"
```

**Files modified:**

- `services/gateway/main.py`
- `services/shared/health.py`
- `services/quant-api/main.py`, `services/finetune-api/main.py`, `services/eval-api/main.py`
- `k8s/base/quant-api/configmap.yaml`, `k8s/base/finetune-api/configmap.yaml`, `k8s/base/eval-api/configmap.yaml`

---

## 25. Service Port Mismatch — port 80 vs containerPort 8000

**Symptom:** `kubectl port-forward -n platform svc/gateway 8000:8000` failed with `Service gateway does not have a service port 8000`. Port-forward only worked with `8000:80`.

**Root Cause:** All four service YAMLs (gateway, quant-api, finetune-api, eval-api) set `port: 80` with `targetPort: 8000`. While technically valid, this contradicts the README's Service URLs table and port-forward commands (which all reference port 8000).

**Fix:** Changed `port: 80` to `port: 8000` in all four service manifests so the service port matches the containerPort:

```yaml
# k8s/base/{gateway,quant-api,finetune-api,eval-api}/service.yaml
ports:
  - port: 8000 # was: 80
    targetPort: 8000
    protocol: TCP
    name: http
```

Applied with `kubectl apply -k k8s/overlays/dev/`. All four services reconfigured. Port-forward now works as documented: `kubectl port-forward -n <ns> svc/<name> 8000:8000`.

**Files modified:**

- `k8s/base/gateway/service.yaml`
- `k8s/base/quant-api/service.yaml`
- `k8s/base/finetune-api/service.yaml`
- `k8s/base/eval-api/service.yaml`

---

## 26. Gateway Route Table Missing Port — upstream_timeout

**Symptom:** `POST /api/quant/predict` returned `{"error": "upstream_timeout"}`. The gateway could not reach team services.

**Root Cause:** Fix #25 changed all service ports from 80 → 8000, but the gateway ConfigMap's `ROUTE_TABLE` and `*_SERVICE_URL` entries still used bare hostnames (e.g. `http://quant-api.quant.svc.cluster.local`), which default to port 80. Since the services no longer listen on port 80, every upstream connection timed out.

**Fix:** Appended `:8000` to all six service URLs in the gateway ConfigMap:

```yaml
# k8s/base/gateway/configmap.yaml
QUANT_SERVICE_URL: "http://quant-api.quant.svc.cluster.local:8000"
FINETUNE_SERVICE_URL: "http://finetune-api.finetune.svc.cluster.local:8000"
EVAL_SERVICE_URL: "http://eval-api.eval.svc.cluster.local:8000"

ROUTE_TABLE: |
  {
    "quant":    { "url": "http://quant-api.quant.svc.cluster.local:8000",    ... },
    "finetune": { "url": "http://finetune-api.finetune.svc.cluster.local:8000", ... },
    "eval":     { "url": "http://eval-api.eval.svc.cluster.local:8000",      ... }
  }
```

Applied with `kubectl apply -k k8s/overlays/dev/`, then `kubectl rollout restart deployment/gateway -n platform`.

**Files modified:**

- `k8s/base/gateway/configmap.yaml`

---

## 27. Dev-Mode Predict Crash — NoneType has no attribute 'invoke'

**Symptom:** After fixing the timeout (fix #26), `POST /api/quant/predict` returned `{"error": "prediction_failed", "message": "'NoneType' object has no attribute 'invoke'"}`.

**Root Cause:** When `SAGEMAKER_ENDPOINT_NAME` is empty (dev mode), all three team services set `app.state.sagemaker = None`. The `/predict` handler unconditionally calls `app.state.sagemaker.invoke(...)`, crashing on `NoneType`.

**Fix:** Created `services/shared/vllm_client.py` — a drop-in `VLLMClient` class that implements the same `.invoke()` and `.check_endpoint_status()` interface as `SageMakerClient`, but forwards requests to the in-cluster vLLM `/v1/completions` endpoint. All three team services now instantiate `VLLMClient()` instead of `None` when no SageMaker endpoint is configured:

```python
# services/shared/vllm_client.py
class VLLMClient:
    """Async vLLM client with the same .invoke() interface as SageMakerClient."""

    async def invoke(self, payload, correlation_id, variant=None) -> dict:
        # Translates {"inputs": ..., "parameters": {...}} → /v1/completions
        # Returns {"generated_text": ..., "model_version": ..., "latency_ms": ...}

    async def check_endpoint_status(self) -> bool:
        # GET /health on vLLM server
```

```python
# services/{quant,finetune,eval}-api/main.py
from shared.vllm_client import VLLMClient
# ...
    if endpoint_name:
        app.state.sagemaker = SageMakerClient(...)
    else:
        app.state.sagemaker = VLLMClient()   # was: None
```

The `VLLMClient` auto-discovers the model name via `/v1/models` and uses `VLLM_BASE_URL` env var (defaulting to `http://mistral-7b-baseline.llm-baseline.svc.cluster.local:8000`).

Rebuilt and pushed all 4 Docker images (`dev-latest`), then restarted all deployments. End-to-end chain now works:

```
gateway → quant-api → VLLMClient → vLLM (Mistral-7B-AWQ) → response (~1.4s)
```

**Files created:**

- `services/shared/vllm_client.py`

**Files modified:**

- `services/quant-api/main.py`
- `services/finetune-api/main.py`
- `services/eval-api/main.py`

---

## 28. EBS CSI Driver Addon — Already Exists

**Symptom:** Attempting to install the EBS CSI driver addon failed:

```
An error occurred (ResourceInUseException) when calling the CreateAddon operation: Addon already exists.
```

**Root Cause:** The `aws-ebs-csi-driver` addon was already installed on the cluster from a prior deployment. Using `create-addon` fails if the addon exists.

**Fix:** Use `update-addon` with `--resolve-conflicts OVERWRITE` instead:

```bash
aws eks update-addon \
  --cluster-name llmplatform-dev \
  --addon-name aws-ebs-csi-driver \
  --service-account-role-arn "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/llmplatform-dev-ebs-csi-driver" \
  --region us-west-2 \
  --resolve-conflicts OVERWRITE
```

Or check current status first:

```bash
aws eks describe-addon \
  --cluster-name llmplatform-dev \
  --addon-name aws-ebs-csi-driver \
  --region us-west-2
```

---

## 29. Grafana — Missing ConfigMaps and Secret (ContainerCreating)

**Symptom:** Grafana pod stuck in `ContainerCreating`:

```
MountVolume.SetUp failed for volume "dashboards" : configmap "grafana-dashboards" not found
MountVolume.SetUp failed for volume "dashboards-provider" : configmap "grafana-dashboards-provider" not found
```

**Root Cause:** `grafana-deployment.yaml` references three resources never defined in any manifest:

- ConfigMap `grafana-dashboards-provider` — dashboard provisioning config
- ConfigMap `grafana-dashboards` — JSON dashboard definitions
- Secret `grafana-secrets` — admin password

**Fix:** Created all three as manifest files so `kubectl apply -f k8s/base/observability/` picks them up on future deployments.

`k8s/base/observability/grafana-dashboards.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards-provider
  namespace: observability
data:
  dashboards.yaml: |
    apiVersion: 1
    providers:
      - name: 'default'
        orgId: 1
        folder: ''
        type: file
        disableDeletion: false
        editable: true
        options:
          path: /var/lib/grafana/dashboards
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboards
  namespace: observability
data:
  llm-platform.json: |
    { ... LLM Platform Overview dashboard JSON ... }
```

`k8s/base/observability/grafana-secrets.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: grafana-secrets
  namespace: observability
type: Opaque
stringData:
  admin-password: admin
```

**Files created:**

- `k8s/base/observability/grafana-dashboards.yaml`
- `k8s/base/observability/grafana-secrets.yaml`

---

## 30. Prometheus + Tempo — Pending (Insufficient CPU/Memory)

**Symptom:** Prometheus and Tempo pods stuck in `Pending`:

```
0/2 nodes are available: 2 Insufficient cpu, 2 Insufficient memory.
persistentvolumeclaim "prometheus-data" not found.
```

PVCs for `prometheus-data` and `tempo-data` were also `Pending` because the StorageClass uses `WaitForFirstConsumer` — PVCs only bind after the pod is scheduled.

**Root Cause:** Two issues:

1. **Resource requests too high for `t3.medium` nodes** (~1.93 vCPU / 3.3 GiB allocatable per node). Prometheus requested `500m` CPU / `1Gi` memory, and both nodes were already at 90-95% utilization from app workloads (eval-api, finetune-api, quant-api, gateway, loki, otel-collector, grafana).

2. **Not enough nodes.** The dev cluster had `desired_size=2` for the general node group. With 6 namespaces of workloads (platform, quant, finetune, eval, observability, kube-system), 2× `t3.medium` is insufficient.

**Fix:**

1. Reduced resource requests:

```yaml
# prometheus-deployment.yaml
resources:
  requests:
    cpu: 100m       # was: 500m
    memory: 256Mi   # was: 1Gi
  limits:
    cpu: "1"        # was: "2"
    memory: 2Gi     # was: 4Gi

# tempo-deployment.yaml
resources:
  requests:
    cpu: 100m       # was: 200m
    memory: 128Mi   # was: 256Mi
  limits:
    cpu: 500m       # was: "1"
    memory: 512Mi   # was: 1Gi
```

2. Scaled general node group from 2 → 4 nodes:

```bash
aws eks update-nodegroup-config \
  --cluster-name llmplatform-dev \
  --nodegroup-name llmplatform-dev-general \
  --scaling-config minSize=2,maxSize=5,desiredSize=4 \
  --region us-west-2
```

3. Updated Terraform to match:

```terraform
# infra/envs/dev/terraform.tfvars
general = {
  instance_types = ["t3.medium"]
  desired_size   = 4    # was: 2
  min_size       = 2    # was: 1
  max_size       = 5    # was: 4
  ...
}
```

After the 3rd and 4th nodes joined, Tempo scheduled immediately. Prometheus required the 4th node because the 3rd was consumed by pending app workloads (quant-api, eval-api replicas).

**Files modified:**

- `k8s/base/observability/prometheus-deployment.yaml`
- `k8s/base/observability/tempo-deployment.yaml`
- `infra/envs/dev/terraform.tfvars`

**Note:** Run `terraform apply` in `infra/envs/dev/` to sync state with the live node group scaling.
