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
        span_name: str = "genai.predict",
        model_variant_type: str = "",
        model_variant_id: str = "",
        sagemaker_endpoint: str = "",
        base_model_id: Optional[str] = None,
        # Accept alternate kwarg names used by team APIs
        tracer=None,
        operation_name: Optional[str] = None,
        model_name: Optional[str] = None,
        variant_type: Optional[str] = None,
        variant_id: Optional[str] = None,
        endpoint_name: Optional[str] = None,
    ):
        # Resolve alternate names (callers pass e.g. operation_name= instead of span_name=)
        self.span_name = operation_name or span_name
        self.model_variant_type = variant_type or model_variant_type
        self.model_variant_id = variant_id or model_variant_id
        self.sagemaker_endpoint = endpoint_name or sagemaker_endpoint
        self.base_model_id = base_model_id
        self.model_name = model_name
        # Use caller's tracer if provided, else the module-level one
        self._tracer = tracer or globals().get("tracer", trace.get_tracer("genai"))
        self.span = None
        self.start_time = None
        self.first_token_time = None

    def __enter__(self):
        self.span = self._tracer.start_span(self.span_name)
        self.start_time = time.perf_counter()

        # Set initial attributes
        self.span.set_attribute("genai.system", "aws.sagemaker")
        self.span.set_attribute("genai.operation.name", "chat.completions")
        self.span.set_attribute("genai.request.model", self.model_variant_id)
        self.span.set_attribute("lab.model.variant.type", self.model_variant_type)
        self.span.set_attribute("lab.model.variant.id", self.model_variant_id)
        self.span.set_attribute("lab.sagemaker.endpoint.name", self.sagemaker_endpoint)

        if self.model_name:
            self.span.set_attribute("lab.model.name", self.model_name)

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
