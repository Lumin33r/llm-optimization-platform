"""Propagation middleware / context injection.

Creates outbound HTTP headers containing W3C Trace Context (traceparent,
tracestate) and W3C Baggage with bounded lab.* keys, as defined in
design-08-otel-schema.md Section 7.
"""

from opentelemetry import baggage
from opentelemetry.propagate import inject
from typing import Dict, Optional


def create_propagation_headers(
    policy_id: str,
    ab_bucket: Optional[str] = None,
    experiment_id: Optional[str] = None,
    promptset_id: Optional[str] = None,
    variant_id: Optional[str] = None
) -> Dict[str, str]:
    """Create headers with trace context and baggage."""

    # Set baggage values
    ctx = baggage.set_baggage("lab.route.policy.id", policy_id)

    if ab_bucket:
        ctx = baggage.set_baggage("lab.ab.bucket", ab_bucket, context=ctx)
    if experiment_id:
        ctx = baggage.set_baggage("lab.experiment.id", experiment_id, context=ctx)
    if promptset_id:
        ctx = baggage.set_baggage("lab.promptset.id", promptset_id, context=ctx)
    if variant_id:
        ctx = baggage.set_baggage("lab.model.variant.id", variant_id, context=ctx)

    # Inject trace context + baggage into headers
    headers = {}
    inject(headers, context=ctx)

    return headers
