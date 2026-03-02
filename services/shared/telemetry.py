"""OpenTelemetry instrumentation for all services.

Sets up tracing, metrics, and structured logging with full resource
attributes as defined in design-08-otel-schema.md Section 1.
"""

import os
from contextlib import contextmanager
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

from shared.logging_config import configure_logging


def _create_resource(service_name: str, namespace: str) -> Resource:
    """Build OTEL Resource with all design-08 required attributes."""
    attrs = {
        SERVICE_NAME: service_name,
        SERVICE_NAMESPACE: namespace,
        "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
        "service.instance.id": os.getenv("POD_UID", f"{service_name}-local"),
        "deployment.environment": os.getenv("ENVIRONMENT", "dev"),
        # Kubernetes attributes
        "k8s.cluster.name": os.getenv("K8S_CLUSTER_NAME", "llmplatform-dev"),
        "k8s.pod.name": os.getenv("POD_NAME", "unknown"),
        "k8s.namespace.name": os.getenv("K8S_NAMESPACE", namespace),
        # Cloud attributes
        "cloud.provider": os.getenv("CLOUD_PROVIDER", "aws"),
        "cloud.region": os.getenv("CLOUD_REGION", "us-west-2"),
        # Lab ownership
        "lab.team": os.getenv("LAB_TEAM", namespace),
        "lab.owner": os.getenv("LAB_OWNER", "platform"),
    }
    return Resource.create(attrs)


def setup_telemetry(app, service_name: str, namespace: str = "platform"):
    """Initialize OpenTelemetry for a FastAPI application."""

    # Build resource with all required attributes (design-08 §1)
    resource = _create_resource(service_name, namespace)

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

    # W3C Trace Context + Baggage propagation is auto-configured by the SDK

    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument HTTP client calls
    HTTPXClientInstrumentor().instrument()

    # Auto-instrument boto3/botocore (SageMaker calls)
    BotocoreInstrumentor().instrument()

    # Structured JSON logging with trace correlation (design-08 §5)
    team = os.getenv("LAB_TEAM", namespace)
    configure_logging(service_name, team)

    return trace.get_tracer(service_name), metrics.get_meter(service_name)


@contextmanager
def create_span(tracer, name: str, attributes: dict = None):
    """Create a custom span with attributes."""
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span
