"""Pydantic models for request/response across team services."""

from pydantic import BaseModel
from typing import Optional


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
