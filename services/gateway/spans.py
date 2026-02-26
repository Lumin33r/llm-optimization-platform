"""Gateway-specific span creation with route attributes.

Sets the lab.route.*, lab.ab.*, and lab.backend.* attributes on Gateway
ingress and backend-call spans as defined in design-08-otel-schema.md
Section 2.
"""

from opentelemetry import trace
from typing import Optional

tracer = trace.get_tracer("gateway")


def set_route_attributes(
    span: trace.Span,
    team: str,
    decision: str,
    reason: str,
    policy_id: str,
    ab_bucket: Optional[str] = None,
    timeout_ms: int = 30000
):
    """Set routing attributes on Gateway ingress span."""
    span.set_attribute("lab.request.kind", "predict")
    span.set_attribute("lab.route.target.team", team)
    span.set_attribute("lab.route.target.service", f"{team}-api")
    span.set_attribute("lab.route.target.endpoint", f"sagemaker:{team}-endpoint")
    span.set_attribute("lab.route.policy.id", policy_id)
    span.set_attribute("lab.route.decision", decision)
    span.set_attribute("lab.route.reason", reason)
    span.set_attribute("lab.timeout.ms", timeout_ms)

    # Model intent mapping
    intent_map = {
        "quant": "quantized",
        "finetune": "finetuned",
        "eval": "evaluator"
    }
    span.set_attribute("lab.model.intent", intent_map.get(team, "unknown"))

    # A/B testing
    span.set_attribute("lab.ab.enabled", ab_bucket is not None)
    if ab_bucket:
        span.set_attribute("lab.ab.bucket", ab_bucket)


def set_backend_call_attributes(
    span: trace.Span,
    team: str,
    ready_at_call: bool,
    retries: int = 0,
    timeout_ms: int = 8000,
    fallback_from: Optional[str] = None,
    fallback_to: Optional[str] = None
):
    """Set attributes on backend proxy span."""
    span.set_attribute("peer.service", f"{team}-api")
    span.set_attribute("lab.backend.ready_at_call", ready_at_call)
    span.set_attribute("lab.backend.retries", retries)
    span.set_attribute("lab.backend.timeout.ms", timeout_ms)

    if fallback_from and fallback_to:
        span.set_attribute("lab.fallback.from", fallback_from)
        span.set_attribute("lab.fallback.to", fallback_to)
