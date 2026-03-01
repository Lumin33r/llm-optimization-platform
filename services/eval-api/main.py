"""Eval Team API - SageMaker wrapper for evaluation/scoring models."""

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
from scorer import EvalScorer


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
            timeout_ms=int(os.getenv("SAGEMAKER_TIMEOUT_MS", "45000")),
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
    title="Eval API",
    description="Evaluation team SageMaker wrapper",
    lifespan=lifespan
)

# Setup telemetry
tracer, meter = setup_telemetry(app, "eval-api", "eval")

# Metrics
predict_counter = meter.create_counter("eval_api.predictions")
predict_latency = meter.create_histogram("eval_api.latency_ms")


# Health Endpoints
@app.get("/startup")
async def startup():
    """Startup probe - returns 200 when initialization complete."""
    if await app.state.health.startup_check():
        return {"status": "started", "service": "eval-api"}
    raise HTTPException(status_code=503, detail="Service starting")


@app.get("/health")
async def health():
    """Liveness probe - returns 200 if process is alive."""
    if await app.state.health.liveness_check():
        return {"status": "healthy", "service": "eval-api", "version": os.getenv("SERVICE_VERSION", "1.0.0")}
    raise HTTPException(status_code=500, detail="Service unhealthy")


@app.get("/ready")
async def ready():
    """Readiness probe - returns 200 if ready for traffic."""
    if await app.state.health.readiness_check():
        return {"status": "ready", "service": "eval-api"}
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
        # Invoke SageMaker
        result = await app.state.sagemaker.invoke(
            payload=payload,
            correlation_id=correlation_id
        )

        latency_ms = (time.time() - start_time) * 1000

        # Record metrics
        predict_counter.add(1, {"status": "success"})
        predict_latency.record(latency_ms)

        return PredictResponse(
            output=result.get("generated_text", result.get("output", "")),
            model_version=result.get("model_version", "unknown"),
            latency_ms=latency_ms,
            correlation_id=correlation_id
        )

    except TimeoutError as e:
        predict_counter.add(1, {"status": "timeout"})
        raise HTTPException(
            status_code=504,
            detail={
                "error": "sagemaker_timeout",
                "message": str(e),
                "correlation_id": correlation_id
            }
        )
    except Exception as e:
        predict_counter.add(1, {"status": "error"})
        raise HTTPException(
            status_code=500,
            detail={
                "error": "prediction_failed",
                "message": str(e),
                "correlation_id": correlation_id
            }
        )


# --------------- Score Endpoint (LLM-as-Judge) ---------------
class ScoreRequest(BaseModel):
    """Request to score a prompt-response pair."""
    prompt: str
    response: str
    threshold_profile: str = "daily-gate-v1"


class ScoreResponse(BaseModel):
    """Quality scores from judge model."""
    eval_id: str
    coherence: float
    helpfulness: float
    factuality: float
    toxicity: float
    pass_threshold: bool
    reasoning: Optional[str] = None


score_counter = meter.create_counter("eval_api.scores")
score_latency = meter.create_histogram("eval_api.score_latency_ms")


@app.post("/score", response_model=ScoreResponse)
async def score(request: ScoreRequest):
    """
    Score a prompt-response pair using the judge model.

    Returns quality scores for coherence, helpfulness, factuality, toxicity
    and whether the response passes the configured threshold profile.
    """
    import time
    start_time = time.time()

    try:
        scorer = EvalScorer(threshold_profile=request.threshold_profile)
        result = await scorer.score(
            prompt=request.prompt,
            response=request.response,
        )

        latency_ms = (time.time() - start_time) * 1000
        score_counter.add(1, {"status": "success", "pass": str(result.pass_threshold)})
        score_latency.record(latency_ms)

        return ScoreResponse(
            eval_id=result.eval_id,
            coherence=result.coherence,
            helpfulness=result.helpfulness,
            factuality=result.factuality,
            toxicity=result.toxicity,
            pass_threshold=result.pass_threshold,
            reasoning=result.reasoning,
        )

    except Exception as e:
        score_counter.add(1, {"status": "error"})
        raise HTTPException(
            status_code=500,
            detail={
                "error": "scoring_failed",
                "message": str(e),
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
            "service": "eval-api"
        }
    )
