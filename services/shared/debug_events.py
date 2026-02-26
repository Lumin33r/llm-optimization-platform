"""Debug event helpers for sampled GenAI prompt/completion inspection.

Adds span events containing hashed prompt/completion references on a
configurable sample of traces, as defined in design-08-otel-schema.md
Section 6. Raw content is never stored — only hashes and optional
encrypted-storage pointers.
"""

import hashlib
import random
from opentelemetry import trace
from typing import Optional

SAMPLING_RATE = 0.01  # 1% of traces get detail events


def should_sample_details() -> bool:
    """Determine if this request should include detail events."""
    return random.random() < SAMPLING_RATE


def prompt_hash(prompt: str) -> str:
    """Generate stable hash for prompt identity."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def add_prompt_event(
    span: trace.Span,
    prompt_hash: str,
    encrypted_ref: Optional[str] = None
):
    """Add prompt detail event to span."""
    span.add_event(
        "genai.prompt",
        attributes={
            "genai.prompt.hash": prompt_hash,
            "lab.redaction.applied": True,
            "lab.payload.encrypted_ref": encrypted_ref or "not_stored"
        }
    )


def add_completion_event(
    span: trace.Span,
    completion_hash: str,
    encrypted_ref: Optional[str] = None
):
    """Add completion detail event to span."""
    span.add_event(
        "genai.completion",
        attributes={
            "genai.completion.hash": completion_hash,
            "lab.redaction.applied": True,
            "lab.payload.encrypted_ref": encrypted_ref or "not_stored"
        }
    )
