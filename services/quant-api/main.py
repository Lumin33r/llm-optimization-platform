"""Quantization Team API - SageMaker wrapper for GPTQ/AWQ models."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uuid

from shared.health import HealthChecker
from shared.sagemaker_client import SageMakerClient
from shared.vllm_client import VLLMClient
from shared.telemetry import setup_telemetry
from shared.genai_spans import GenAISpanContext
from shared.debug_events import should_sample_details, prompt_hash, add_prompt_event, add_completion_event


# Request/Response Models
class PredictRequest(BaseModel):
    """Prediction request payload."""
    prompt: str
    max_tokens: int = 256
    temperature: float = 0.7
    model_params: Optional[dict] = None


class PredictResponse(BaseModel):
    """Prediction response."""
    output: str
    model_version: str
    latency_ms: float
    correlation_id: str


# Lifespan for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    # Startup — SageMaker client is optional (may not exist in dev)
    endpoint_name = os.getenv("SAGEMAKER_ENDPOINT_NAME", "")
    if endpoint_name:
        app.state.sagemaker = SageMakerClient(
            endpoint_name=endpoint_name,
            timeout_ms=int(os.getenv("SAGEMAKER_TIMEOUT_MS", "30000")),
            enable_fallback=os.getenv("ENABLE_FALLBACK", "false").lower() == "true"
        )
    else:
        app.state.sagemaker = VLLMClient()
    app.state.health = HealthChecker(app.state.sagemaker)

    yield

    # Cleanup
    pass


# Create app
app = FastAPI(
    title="Quant API",
    description="Quantization team SageMaker wrapper",
    lifespan=lifespan
)

# Setup telemetry
tracer, meter = setup_telemetry(app, "quant-api", "quant")

# Metrics (design-08 §4 naming)
predict_counter = meter.create_counter("lab_service_requests_total")
predict_latency = meter.create_histogram("lab_llm_e2e_duration_ms")
ttft_histogram = meter.create_histogram("lab_llm_ttft_ms")
sagemaker_error_counter = meter.create_counter("lab_service_sagemaker_errors_total")


# Health Endpoints
@app.get("/startup")
async def startup():
    """Startup probe - returns 200 when initialization complete."""
    if await app.state.health.startup_check():
        return {"status": "started", "service": "quant-api"}
    raise HTTPException(status_code=503, detail="Service starting")


@app.get("/health")
async def health():
    """Liveness probe - returns 200 if process is alive."""
    if await app.state.health.liveness_check():
        return {"status": "healthy", "service": "quant-api", "version": os.getenv("SERVICE_VERSION", "1.0.0")}
    raise HTTPException(status_code=500, detail="Service unhealthy")


@app.get("/ready")
async def ready():
    """Readiness probe - returns 200 if ready for traffic."""
    if await app.state.health.readiness_check():
        return {"status": "ready", "service": "quant-api"}
    raise HTTPException(status_code=503, detail="Service not ready")


# Prediction Endpoint
@app.post("/predict", response_model=PredictResponse)
async def predict(
    request: PredictRequest,
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
):
    """
    Run inference through SageMaker endpoint.

    Headers:
        X-Correlation-ID: Request correlation ID (generated if not provided)

    Returns:
        PredictResponse with model output and metadata
    """
    import time
    start_time = time.time()

    # Generate correlation ID if not provided
    correlation_id = x_correlation_id or str(uuid.uuid4())

    # Build SageMaker payload
    payload = {
        "inputs": request.prompt,
        "parameters": {
            "max_new_tokens": request.max_tokens,
            "temperature": request.temperature,
            **(request.model_params or {})
        }
    }

    try:
        # GenAI span with semantic conventions (design-08 §3)
        with GenAISpanContext(
            tracer=tracer,
            operation_name="predict",
            model_name="Mistral-7B-AWQ",
            variant_type="awq",
            variant_id=os.getenv("MODEL_VARIANT_ID", "quant-awq-v1"),
            endpoint_name=os.getenv("SAGEMAKER_ENDPOINT_NAME", "local-vllm"),
        ) as genai_span:
            # Debug events on sampled traces (design-08 §6)
            if should_sample_details():
                add_prompt_event(genai_span, prompt_hash(request.prompt))

            # Invoke SageMaker / vLLM
            result = await app.state.sagemaker.invoke(
                payload=payload,
                correlation_id=correlation_id
            )

            # Record token metrics on the span
            genai_span.record_completion(
                input_tokens=result.get("input_tokens", 0),
                output_tokens=result.get("output_tokens", 0),
            )

            # Debug: completion event
            if should_sample_details():
                output_text = result.get("generated_text", "")
                add_completion_event(genai_span, prompt_hash(output_text))

        latency_ms = (time.time() - start_time) * 1000

        # Record metrics
        predict_counter.add(1, {"status": "success", "team": "quant"})
        predict_latency.record(latency_ms, {"team": "quant"})

        return PredictResponse(
            output=result.get("generated_text", result.get("output", "")),
            model_version=result.get("model_version", "unknown"),
            latency_ms=latency_ms,
            correlation_id=correlation_id
        )

    except TimeoutError as e:
        predict_counter.add(1, {"status": "timeout", "team": "quant"})
        sagemaker_error_counter.add(1, {"team": "quant", "error_type": "timeout"})
        raise HTTPException(
            status_code=504,
            detail={
                "error": "sagemaker_timeout",
                "message": str(e),
                "correlation_id": correlation_id
            }
        )
    except Exception as e:
        predict_counter.add(1, {"status": "error", "team": "quant"})
        sagemaker_error_counter.add(1, {"team": "quant", "error_type": type(e).__name__})
        raise HTTPException(
            status_code=500,
            detail={
                "error": "prediction_failed",
                "message": str(e),
                "correlation_id": correlation_id
            }
        )


# Error handlers
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": str(exc),
            "service": "quant-api"
        }
    )
