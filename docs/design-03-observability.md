# Design Document 3: Observability Stack

## Overview

This document defines the observability architecture for the LLM Optimization Platform. The stack is **Grafana-centric** with OpenTelemetry Collector as the central telemetry ingestion point.

**Key Principles**:

- **OTEL-first** - All services emit telemetry via OpenTelemetry SDKs
- **Central collection** - OTEL Collector receives all metrics, logs, traces
- **Unified visualization** - Grafana as single pane of glass
- **Trace correlation** - Request traces flow Gateway → Team Service → SageMaker

---

## Quick Start (Implementation Order)

```bash
# 1. Prerequisites (after design-02 kubectl configured)
kubectl create namespace observability

# 2. Deploy OTEL Collector first
kubectl apply -f k8s/base/observability/otel-collector-config.yaml
kubectl apply -f k8s/base/observability/otel-collector-deployment.yaml

# 3. Deploy storage backends
kubectl apply -f k8s/base/observability/prometheus.yaml
kubectl apply -f k8s/base/observability/loki.yaml
kubectl apply -f k8s/base/observability/tempo.yaml

# 4. Deploy Grafana with datasources
kubectl apply -f k8s/base/observability/grafana.yaml

# 5. Verify telemetry flow
kubectl logs -n observability -l app=otel-collector --tail=20
```

**Depends On**: [design-02-kubernetes.md](design-02-kubernetes.md) (namespaces)
**Feeds Into**: [design-08-otel-schema.md](design-08-otel-schema.md) (attribute schema)

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                              Observability Namespace                                      │
│                                                                                          │
│    ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│    │                           OpenTelemetry Collector                                │  │
│    │                    (Central OTLP Ingestion Point)                               │  │
│    │                                                                                  │  │
│    │   OTLP Receiver ───────┬─────────────┬─────────────┬──────────────────────────│  │
│    │   :4317 (gRPC)         │             │             │                           │  │
│    │   :4318 (HTTP)         ▼             ▼             ▼                           │  │
│    │                   ┌─────────┐   ┌─────────┐   ┌─────────┐                      │  │
│    │                   │ Metrics │   │  Logs   │   │ Traces  │                      │  │
│    │                   │Exporter │   │Exporter │   │Exporter │                      │  │
│    │                   └────┬────┘   └────┬────┘   └────┬────┘                      │  │
│    └────────────────────────┼─────────────┼─────────────┼───────────────────────────┘  │
│                             │             │             │                              │
│                             ▼             ▼             ▼                              │
│    ┌─────────────────┐ ┌─────────────┐ ┌─────────────┐                                │
│    │   Prometheus    │ │    Loki     │ │    Tempo    │                                │
│    │     /Mimir      │ │             │ │             │                                │
│    │                 │ │ Log Store   │ │ Trace Store │                                │
│    │  Metrics TSDB   │ │             │ │             │                                │
│    └────────┬────────┘ └──────┬──────┘ └──────┬──────┘                                │
│             │                 │               │                                        │
│             └─────────────────┼───────────────┘                                        │
│                               ▼                                                        │
│                        ┌─────────────────────────────────────────────────────────┐    │
│                        │                    Grafana                               │    │
│                        │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐ │    │
│                        │  │ Prometheus │  │   Loki     │  │      Tempo         │ │    │
│                        │  │ Datasource │  │ Datasource │  │   Datasource       │ │    │
│                        │  └────────────┘  └────────────┘  └────────────────────┘ │    │
│                        │                                                          │    │
│                        │  ┌──────────────────────────────────────────────────┐   │    │
│                        │  │         LLM Platform Operations Plugin           │   │    │
│                        │  │   (React Panel - see design-06-dashboard.md)     │   │    │
│                        │  └──────────────────────────────────────────────────┘   │    │
│                        └─────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ Telemetry
            ┌───────────────────────┼───────────────────────┬───────────────────────┐
            │                       │                       │                       │
     ┌──────┴──────┐         ┌──────┴──────┐         ┌──────┴──────┐         ┌──────┴──────┐
     │   Gateway   │         │  Team APIs  │         │   vLLM      │         │  K8s/AWS    │
     │  (platform) │         │(quant/ft/ev)│         │llm-baseline │         │  Telemetry  │
     └─────────────┘         └─────────────┘         └─────────────┘         └─────────────┘
```

> **Note**: The vLLM baseline model (see [design-10-models.md](design-10-models.md)) exposes native Prometheus metrics at `/metrics` which are scraped directly by OTEL Collector's Prometheus receiver.

---

## Component Stack

| Component        | Purpose                     | Port(s)                                  | Namespace     |
| ---------------- | --------------------------- | ---------------------------------------- | ------------- |
| OTEL Collector   | Central telemetry ingestion | 4317 (gRPC), 4318 (HTTP), 8888 (metrics) | observability |
| Prometheus/Mimir | Metrics storage (TSDB)      | 9090                                     | observability |
| Loki             | Log aggregation             | 3100                                     | observability |
| Tempo            | Distributed tracing         | 3200, 9411                               | observability |
| Grafana          | Visualization + dashboards  | 3000                                     | observability |

---

## OpenTelemetry Collector Configuration

### Deployment

```yaml
# k8s/base/observability/otel-collector-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: otel-collector
  namespace: observability
  labels:
    app: otel-collector
spec:
  replicas: 2
  selector:
    matchLabels:
      app: otel-collector
  template:
    metadata:
      labels:
        app: otel-collector
    spec:
      containers:
        - name: otel-collector
          image: otel/opentelemetry-collector-contrib:0.95.0
          args: ["--config=/etc/otel/config.yaml"]
          ports:
            - containerPort: 4317 # OTLP gRPC
              name: otlp-grpc
            - containerPort: 4318 # OTLP HTTP
              name: otlp-http
            - containerPort: 8888 # Prometheus metrics
              name: metrics
          volumeMounts:
            - name: config
              mountPath: /etc/otel
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 1Gi
          livenessProbe:
            httpGet:
              path: /
              port: 13133
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: /
              port: 13133
            periodSeconds: 5
      volumes:
        - name: config
          configMap:
            name: otel-collector-config
---
apiVersion: v1
kind: Service
metadata:
  name: otel-collector
  namespace: observability
spec:
  type: ClusterIP
  selector:
    app: otel-collector
  ports:
    - port: 4317
      targetPort: 4317
      name: otlp-grpc
    - port: 4318
      targetPort: 4318
      name: otlp-http
    - port: 8888
      targetPort: 8888
      name: metrics
```

### Collector Configuration

```yaml
# k8s/base/observability/otel-collector-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-collector-config
  namespace: observability
data:
  config.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318

      # Kubernetes cluster metrics
      k8s_cluster:
        collection_interval: 30s
        node_conditions_to_report: [Ready, MemoryPressure, DiskPressure]
        allocatable_types_to_report: [cpu, memory]

      # Prometheus scraping for services that expose /metrics
      prometheus:
        config:
          scrape_configs:
            - job_name: 'kubernetes-pods'
              kubernetes_sd_configs:
                - role: pod
              relabel_configs:
                - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
                  action: keep
                  regex: true
                - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
                  action: replace
                  regex: ([^:]+)(?::\d+)?;(\d+)
                  replacement: $1:$2
                  target_label: __address__

    processors:
      batch:
        send_batch_size: 10000
        timeout: 10s

      memory_limiter:
        check_interval: 1s
        limit_mib: 800
        spike_limit_mib: 200

      # Add resource attributes
      resource:
        attributes:
          - key: deployment.environment
            value: "${ENVIRONMENT}"
            action: upsert
          - key: service.namespace
            from_attribute: k8s.namespace.name
            action: upsert

      # Enrich with K8s metadata
      k8sattributes:
        auth_type: serviceAccount
        passthrough: false
        extract:
          metadata:
            - k8s.pod.name
            - k8s.pod.uid
            - k8s.deployment.name
            - k8s.namespace.name
            - k8s.node.name
          labels:
            - tag_name: app
              key: app
              from: pod
            - tag_name: team
              key: team
              from: pod

    exporters:
      # Prometheus Remote Write (for Mimir/Prometheus)
      prometheusremotewrite:
        endpoint: "http://prometheus:9090/api/v1/write"
        tls:
          insecure: true

      # Loki for logs
      loki:
        endpoint: "http://loki:3100/loki/api/v1/push"
        labels:
          attributes:
            - service.name
            - service.namespace
            - k8s.pod.name
            - level

      # Tempo for traces
      otlp/tempo:
        endpoint: "tempo:4317"
        tls:
          insecure: true

      # Debug logging
      logging:
        loglevel: info

    extensions:
      health_check:
        endpoint: 0.0.0.0:13133
      zpages:
        endpoint: 0.0.0.0:55679

    service:
      extensions: [health_check, zpages]
      pipelines:
        metrics:
          receivers: [otlp, prometheus, k8s_cluster]
          processors: [memory_limiter, batch, resource, k8sattributes]
          exporters: [prometheusremotewrite]

        logs:
          receivers: [otlp]
          processors: [memory_limiter, batch, resource, k8sattributes]
          exporters: [loki]

        traces:
          receivers: [otlp]
          processors: [memory_limiter, batch, resource, k8sattributes]
          exporters: [otlp/tempo]
```

---

## Service Instrumentation

### Python SDK Configuration (FastAPI Services)

```python
# services/shared/telemetry.py
"""OpenTelemetry instrumentation for all services."""

import os
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation import TraceContextTextMapPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator


def setup_telemetry(app, service_name: str, namespace: str = "platform"):
    """Initialize OpenTelemetry for a FastAPI application."""

    # Define resource attributes
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_NAMESPACE: namespace,
        "deployment.environment": os.getenv("ENVIRONMENT", "dev"),
    })

    # OTLP endpoint from environment
    otlp_endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.observability.svc.cluster.local:4317"
    )

    # Setup tracing
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
    )
    trace.set_tracer_provider(trace_provider)

    # Setup metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
        export_interval_millis=30000
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Use W3C Trace Context + Baggage propagation (matches design-08 schema)
    set_global_textmap(CompositePropagator([
        TraceContextTextMapPropagator(),
        W3CBaggagePropagator()
    ]))

    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument HTTP client calls
    HTTPXClientInstrumentor().instrument()

    # Auto-instrument boto3/botocore (SageMaker calls)
    BotocoreInstrumentor().instrument()

    return trace.get_tracer(service_name), metrics.get_meter(service_name)


from contextlib import contextmanager


@contextmanager
def create_span(tracer, name: str, attributes: dict = None):
    """Create a custom span with attributes."""
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span
```

### Usage in Service

```python
# services/gateway/main.py
from fastapi import FastAPI, Request
from shared.telemetry import setup_telemetry
from opentelemetry import trace

app = FastAPI(title="Gateway API")

# Initialize telemetry
tracer, meter = setup_telemetry(app, "gateway", "platform")

# Create custom metrics
request_counter = meter.create_counter(
    "gateway.requests",
    description="Total requests by team"
)

latency_histogram = meter.create_histogram(
    "gateway.latency_ms",
    description="Request latency in milliseconds"
)


@app.post("/api/{team}/predict")
async def predict(team: str, request: Request):
    """Route prediction request to team service."""

    # Get current span and add attributes
    current_span = trace.get_current_span()
    current_span.set_attribute("team", team)
    current_span.set_attribute("correlation_id", request.headers.get("X-Correlation-ID"))

    # Record metric
    request_counter.add(1, {"team": team})

    # ... route to team service
```

---

## Trace Flow: Gateway → Team → SageMaker

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              Request Trace                                        │
│                                                                                   │
│  Trace ID: abc123                                                                │
│                                                                                   │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ Span: gateway.predict                                                       │ │
│  │ Service: gateway | Duration: 523ms                                         │ │
│  │ Attributes:                                                                 │ │
│  │   - team: quant                                                            │ │
│  │   - correlation_id: req-456                                                │ │
│  │   - http.method: POST                                                      │ │
│  │   - http.route: /api/{team}/predict                                        │ │
│  │                                                                             │ │
│  │   ┌──────────────────────────────────────────────────────────────────────┐│ │
│  │   │ Span: quant-api.predict                                              ││ │
│  │   │ Service: quant-api | Duration: 498ms                                 ││ │
│  │   │ Attributes:                                                          ││ │
│  │   │   - sagemaker.endpoint: quant-endpoint                               ││ │
│  │   │   - model.version: v1.2.0                                            ││ │
│  │   │                                                                      ││ │
│  │   │   ┌────────────────────────────────────────────────────────────────┐││ │
│  │   │   │ Span: sagemaker.invoke_endpoint                                │││ │
│  │   │   │ Service: AWS SageMaker | Duration: 412ms                       │││ │
│  │   │   │ Attributes:                                                    │││ │
│  │   │   │   - aws.service: sagemaker                                     │││ │
│  │   │   │   - aws.operation: InvokeEndpoint                              │││ │
│  │   │   │   - aws.region: us-west-2                                      │││ │
│  │   │   └────────────────────────────────────────────────────────────────┘││ │
│  │   └──────────────────────────────────────────────────────────────────────┘│ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Prometheus / Mimir Configuration

### Prometheus Deployment

```yaml
# k8s/base/observability/prometheus-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: observability
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      containers:
        - name: prometheus
          image: prom/prometheus:v2.49.0
          args:
            - "--config.file=/etc/prometheus/prometheus.yml"
            - "--storage.tsdb.path=/prometheus"
            - "--storage.tsdb.retention.time=15d"
            - "--web.enable-remote-write-receiver"
            - "--web.enable-lifecycle"
          ports:
            - containerPort: 9090
          volumeMounts:
            - name: config
              mountPath: /etc/prometheus
            - name: data
              mountPath: /prometheus
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: "2"
              memory: 4Gi
      volumes:
        - name: config
          configMap:
            name: prometheus-config
        - name: data
          persistentVolumeClaim:
            claimName: prometheus-data
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: prometheus-data
  namespace: observability
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 50Gi
  storageClassName: gp3
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: observability
spec:
  selector:
    app: prometheus
  ports:
    - port: 9090
      targetPort: 9090
```

### Prometheus Config

```yaml
# k8s/base/observability/prometheus-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: observability
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
      evaluation_interval: 15s

    scrape_configs:
      # Scrape OTEL Collector metrics
      - job_name: 'otel-collector'
        static_configs:
          - targets: ['otel-collector:8888']

      # Scrape Prometheus itself
      - job_name: 'prometheus'
        static_configs:
          - targets: ['localhost:9090']
```

---

## Loki Configuration

```yaml
# k8s/base/observability/loki-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: loki
  namespace: observability
spec:
  replicas: 1
  selector:
    matchLabels:
      app: loki
  template:
    metadata:
      labels:
        app: loki
    spec:
      containers:
        - name: loki
          image: grafana/loki:3.0.0
          args: ["-config.file=/etc/loki/config.yaml"]
          ports:
            - containerPort: 3100
          volumeMounts:
            - name: config
              mountPath: /etc/loki
            - name: data
              mountPath: /loki
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 1Gi
      volumes:
        - name: config
          configMap:
            name: loki-config
        - name: data
          persistentVolumeClaim:
            claimName: loki-data
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: loki-data
  namespace: observability
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 50Gi
  storageClassName: gp3
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: loki-config
  namespace: observability
data:
  config.yaml: |
    auth_enabled: false

    server:
      http_listen_port: 3100

    common:
      path_prefix: /loki
      storage:
        filesystem:
          chunks_directory: /loki/chunks
          rules_directory: /loki/rules
      replication_factor: 1
      ring:
        kvstore:
          store: inmemory

    schema_config:
      configs:
        - from: 2024-01-01
          store: tsdb
          object_store: filesystem
          schema: v13
          index:
            prefix: index_
            period: 24h

    limits_config:
      enforce_metric_name: false
      reject_old_samples: true
      reject_old_samples_max_age: 168h
---
apiVersion: v1
kind: Service
metadata:
  name: loki
  namespace: observability
spec:
  selector:
    app: loki
  ports:
    - port: 3100
      targetPort: 3100
```

---

## Tempo Configuration

```yaml
# k8s/base/observability/tempo-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tempo
  namespace: observability
spec:
  replicas: 1
  selector:
    matchLabels:
      app: tempo
  template:
    metadata:
      labels:
        app: tempo
    spec:
      containers:
        - name: tempo
          image: grafana/tempo:2.3.1
          args: ["-config.file=/etc/tempo/config.yaml"]
          ports:
            - containerPort: 3200 # Tempo HTTP
              name: http
            - containerPort: 4317 # OTLP gRPC
              name: otlp-grpc
            - containerPort: 9411 # Zipkin
              name: zipkin
          volumeMounts:
            - name: config
              mountPath: /etc/tempo
            - name: data
              mountPath: /var/tempo
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 1Gi
      volumes:
        - name: config
          configMap:
            name: tempo-config
        - name: data
          persistentVolumeClaim:
            claimName: tempo-data
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: tempo-data
  namespace: observability
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 20Gi
  storageClassName: gp3
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: tempo-config
  namespace: observability
data:
  config.yaml: |
    server:
      http_listen_port: 3200

    distributor:
      receivers:
        otlp:
          protocols:
            grpc:
              endpoint: 0.0.0.0:4317
            http:
              endpoint: 0.0.0.0:4318
        zipkin:
          endpoint: 0.0.0.0:9411

    ingester:
      trace_idle_period: 10s
      max_block_bytes: 1_000_000
      max_block_duration: 5m

    compactor:
      compaction:
        block_retention: 48h

    storage:
      trace:
        backend: local
        local:
          path: /var/tempo/traces
        wal:
          path: /var/tempo/wal
---
apiVersion: v1
kind: Service
metadata:
  name: tempo
  namespace: observability
spec:
  selector:
    app: tempo
  ports:
    - port: 3200
      targetPort: 3200
      name: http
    - port: 4317
      targetPort: 4317
      name: otlp-grpc
    - port: 9411
      targetPort: 9411
      name: zipkin
```

---

## Grafana Configuration

### Architecture: Nginx Reverse Proxy Sidecar

The Grafana pod uses an **nginx sidecar** to solve browser-to-gateway connectivity.
The Grafana plugin makes client-side `fetch()` calls, so it cannot use K8s internal
DNS names (browsers can't resolve `.svc.cluster.local`). The nginx sidecar
reverse-proxies `/gateway-proxy/` to the gateway's internal DNS, allowing the
plugin to use a relative URL (`/gateway-proxy`) that works from any browser.

```
Browser :3000 → nginx → /             → Grafana :3001
                      → /gateway-proxy/ → gateway.platform.svc:8000
```

### Deployment

```yaml
# k8s/base/observability/grafana-deployment.yaml
#
# nginx sidecar reverse-proxies browser requests so the
# Grafana plugin can reach the gateway via a relative URL (/gateway-proxy/)
# instead of needing the external ELB hostname.
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-nginx-conf
  namespace: observability
data:
  default.conf: |
    server {
        listen 3000;
        client_max_body_size 10m;

        location / {
            proxy_pass http://127.0.0.1:3001;
            proxy_set_header Host $host;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        location /gateway-proxy/ {
            proxy_pass http://gateway.platform.svc.cluster.local:8000/;
            proxy_set_header Host $host;
            proxy_connect_timeout 10s;
            proxy_read_timeout 120s;
        }
    }
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
  namespace: observability
spec:
  replicas: 1
  selector:
    matchLabels:
      app: grafana
  template:
    metadata:
      labels:
        app: grafana
    spec:
      containers:
        # --- nginx reverse proxy (port 3000, user-facing) ---
        - name: nginx-proxy
          image: nginx:1.25-alpine
          ports:
            - containerPort: 3000
          volumeMounts:
            - name: nginx-conf
              mountPath: /etc/nginx/conf.d
          resources:
            requests:
              cpu: 50m
              memory: 32Mi
            limits:
              cpu: 200m
              memory: 64Mi
        # --- Grafana (port 3001, internal only) ---
        - name: grafana
          image: 388691194728.dkr.ecr.us-west-2.amazonaws.com/llmplatform-dev/grafana-plugin:dev-latest
          imagePullPolicy: Always
          ports:
            - containerPort: 3001
          env:
            - name: GF_SERVER_HTTP_PORT
              value: "3001"
            - name: GF_SECURITY_ADMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: grafana-secrets
                  key: admin-password
            - name: GF_INSTALL_PLUGINS
              value: "grafana-clock-panel,grafana-piechart-panel"
            - name: GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS
              value: "llmplatform-ops-panel"
          volumeMounts:
            - name: datasources
              mountPath: /etc/grafana/provisioning/datasources
            - name: dashboards-provider
              mountPath: /etc/grafana/provisioning/dashboards
            - name: dashboards
              mountPath: /var/lib/grafana/dashboards
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 1Gi
      volumes:
        - name: nginx-conf
          configMap:
            name: grafana-nginx-conf
        - name: datasources
          configMap:
            name: grafana-datasources
        - name: dashboards-provider
          configMap:
            name: grafana-dashboards-provider
        - name: dashboards
          configMap:
            name: grafana-dashboards
---
apiVersion: v1
kind: Service
metadata:
  name: grafana
  namespace: observability
spec:
  type: LoadBalancer
  selector:
    app: grafana
  ports:
    - port: 3000
      targetPort: 3000
```

### Datasources Configuration

```yaml
# k8s/base/observability/grafana-datasources.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-datasources
  namespace: observability
data:
  datasources.yaml: |
    apiVersion: 1

    datasources:
      - name: Prometheus
        type: prometheus
        access: proxy
        url: http://prometheus:9090
        isDefault: true
        editable: false

      - name: Loki
        type: loki
        access: proxy
        url: http://loki:3100
        editable: false
        jsonData:
          derivedFields:
            - name: TraceID
              matcherRegex: '"trace_id":"([^"]+)"'
              url: '$${__value.raw}'
              datasourceUid: tempo

      - name: Tempo
        type: tempo
        access: proxy
        url: http://tempo:3200
        uid: tempo
        editable: false
        jsonData:
          httpMethod: GET
          tracesToLogs:
            datasourceUid: loki
            tags: ['service.name', 'k8s.pod.name']
          serviceMap:
            datasourceUid: prometheus
          nodeGraph:
            enabled: true
```

---

## Key Metrics to Track

### Service Health Metrics

```promql
# Request rate by service
sum(rate(http_server_request_count_total[5m])) by (service_name)

# Error rate by service
sum(rate(http_server_request_count_total{http_status_code=~"5.."}[5m])) by (service_name)
/ sum(rate(http_server_request_count_total[5m])) by (service_name)

# P95 latency by service
histogram_quantile(0.95,
  sum(rate(http_server_request_duration_seconds_bucket[5m])) by (le, service_name)
)
```

### SageMaker Metrics

```promql
# SageMaker invoke latency
histogram_quantile(0.95,
  sum(rate(sagemaker_invoke_duration_seconds_bucket[5m])) by (le, endpoint)
)

# SageMaker error rate
sum(rate(sagemaker_invoke_errors_total[5m])) by (endpoint)
```

### Kubernetes Metrics

```promql
# Pod restart count
sum(kube_pod_container_status_restarts_total) by (namespace, pod)

# Resource utilization
sum(container_memory_usage_bytes) by (namespace)
/ sum(kube_resourcequota{resource="limits.memory"}) by (namespace)

# Pod readiness
sum(kube_pod_status_ready{condition="true"}) by (namespace)
/ sum(kube_pod_status_ready) by (namespace)
```

---

## Controlled Failure Observability

### 1. Detecting Probe Restarts

```promql
# Alert: Pod restarted due to liveness failure
increase(kube_pod_container_status_restarts_total[5m]) > 0
```

### 2. Detecting Quota Rejections

```yaml
# Loki query for quota rejection events
{namespace="quant"} |= "exceeded quota"
```

### 3. Detecting Readiness Gate

```promql
# Pods not ready
kube_pod_status_ready{condition="false"} == 1
```

### 4. Detecting SageMaker Timeouts

```promql
# SageMaker timeout errors
sum(rate(sagemaker_invoke_errors_total{error_type="timeout"}[5m])) by (endpoint)
```

---

## Dashboard Templates

### Platform Overview Dashboard

```json
{
  "title": "LLM Platform Overview",
  "panels": [
    {
      "title": "Request Rate",
      "type": "stat",
      "targets": [{ "expr": "sum(rate(gateway_requests_total[5m]))" }]
    },
    {
      "title": "Error Rate",
      "type": "gauge",
      "targets": [
        {
          "expr": "sum(rate(gateway_requests_total{status=~\"5..\"}[5m])) / sum(rate(gateway_requests_total[5m]))"
        }
      ]
    },
    {
      "title": "Team Request Distribution",
      "type": "piechart",
      "targets": [
        { "expr": "sum(increase(gateway_requests_total[1h])) by (team)" }
      ]
    },
    {
      "title": "P95 Latency by Team",
      "type": "timeseries",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, sum(rate(gateway_latency_ms_bucket[5m])) by (le, team))"
        }
      ]
    }
  ]
}
```

---

## Implementation Checklist

- [ ] Deploy OTEL Collector with complete pipeline config
- [ ] Deploy Prometheus with remote write enabled
- [ ] Deploy Loki for log aggregation
- [ ] Deploy Tempo for distributed tracing
- [ ] Deploy Grafana with datasources provisioned
- [ ] Configure OTEL SDK in all services (Gateway, team APIs)
- [ ] Verify trace propagation: Gateway → Team → SageMaker
- [ ] Create custom metrics (request counters, latency histograms)
- [ ] Import platform overview dashboard
- [ ] Set up alerting rules for controlled failure scenarios
- [ ] Test log-to-trace correlation in Grafana
