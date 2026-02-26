"""GenAI span helpers for LLM-specific attributes.

Provides context managers and utilities for creating OpenTelemetry spans
that follow the GenAI semantic conventions and the lab.* attribute schema
defined in design-08-otel-schema.md.
"""

from opentelemetry import trace
from typing import Optional
import time

tracer = trace.get_tracer("genai")


class GenAISpanContext:
    """Context manager for GenAI inference spans with timing."""

    def __init__(
        self,
        span_name: str,
        model_variant_type: str,
        model_variant_id: str,
        sagemaker_endpoint: str,
        base_model_id: Optional[str] = None
    ):
        self.span_name = span_name
        self.model_variant_type = model_variant_type
        self.model_variant_id = model_variant_id
        self.sagemaker_endpoint = sagemaker_endpoint
        self.base_model_id = base_model_id
        self.span = None
        self.start_time = None
        self.first_token_time = None

    def __enter__(self):
        self.span = tracer.start_span(self.span_name)
        self.start_time = time.perf_counter()

        # Set initial attributes
        self.span.set_attribute("genai.system", "aws.sagemaker")
        self.span.set_attribute("genai.operation.name", "chat.completions")
        self.span.set_attribute("genai.request.model", self.model_variant_id)
        self.span.set_attribute("lab.model.variant.type", self.model_variant_type)
        self.span.set_attribute("lab.model.variant.id", self.model_variant_id)
        self.span.set_attribute("lab.sagemaker.endpoint.name", self.sagemaker_endpoint)

        if self.base_model_id:
            self.span.set_attribute("lab.model.base.id", self.base_model_id)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.span.set_attribute("error.type", exc_type.__name__)
            self.span.set_attribute("error.message", str(exc_val)[:200])
        self.span.end()

    def record_first_token(self):
        """Call when first token is received (streaming)."""
        self.first_token_time = time.perf_counter()
        ttft_ms = (self.first_token_time - self.start_time) * 1000
        self.span.set_attribute("lab.llm.ttft.ms", int(ttft_ms))

    def record_completion(
        self,
        input_tokens: int,
        output_tokens: int,
        response_model: Optional[str] = None
    ):
        """Record completion metrics."""
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        self.span.set_attribute("genai.usage.input_tokens", input_tokens)
        self.span.set_attribute("genai.usage.output_tokens", output_tokens)
        self.span.set_attribute("genai.usage.total_tokens", input_tokens + output_tokens)

        if response_model:
            self.span.set_attribute("genai.response.model", response_model)

        if output_tokens > 0:
            tpot_ms = duration_ms / output_tokens
            tokens_per_sec = (output_tokens / duration_ms) * 1000
            self.span.set_attribute("lab.llm.tpot.ms", int(tpot_ms))
            self.span.set_attribute("lab.llm.tokens_per_sec", round(tokens_per_sec, 1))
