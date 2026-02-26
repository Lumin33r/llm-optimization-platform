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
