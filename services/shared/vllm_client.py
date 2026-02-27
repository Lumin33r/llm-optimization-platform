"""vLLM inference client - drop-in replacement for SageMakerClient in dev mode."""

import os
import time
from typing import Optional, Dict, Any

import httpx
from opentelemetry import trace


class VLLMClient:
    """Async vLLM client with the same .invoke() interface as SageMakerClient."""

    def __init__(
        self,
        base_url: str = "",
        timeout_ms: int = 60000,
        model: str = "",
    ):
        self.base_url = base_url or os.getenv(
            "VLLM_BASE_URL",
            "http://mistral-7b-baseline.llm-baseline.svc.cluster.local:8000",
        )
        self.model = model or os.getenv("VLLM_MODEL", "")
        self.timeout_seconds = timeout_ms / 1000
        self.tracer = trace.get_tracer(__name__)
        self._http = httpx.AsyncClient(timeout=self.timeout_seconds)

    # ------------------------------------------------------------------
    # Public interface (matches SageMakerClient)
    # ------------------------------------------------------------------

    async def invoke(
        self,
        payload: Dict[str, Any],
        correlation_id: str,
        variant: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Forward an inference request to the vLLM /v1/completions endpoint.

        Accepts the same *payload* shape the team services already build:
            {"inputs": "<prompt>", "parameters": {"max_new_tokens": N, ...}}

        Returns a dict with at least ``generated_text`` so the existing
        PredictResponse mapping works unchanged.
        """
        with self.tracer.start_as_current_span("vllm.invoke") as span:
            span.set_attribute("vllm.base_url", self.base_url)
            span.set_attribute("correlation_id", correlation_id)

            prompt = payload.get("inputs", "")
            params = payload.get("parameters", {})

            # Resolve model name lazily (allows discovery after startup)
            model = self.model
            if not model:
                model = await self._discover_model()

            body = {
                "model": model,
                "prompt": prompt,
                "max_tokens": params.get("max_new_tokens", 256),
                "temperature": params.get("temperature", 0.7),
            }

            try:
                start = time.time()
                resp = await self._http.post(
                    f"{self.base_url}/v1/completions",
                    json=body,
                    headers={
                        "X-Correlation-ID": correlation_id,
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                latency_ms = (time.time() - start) * 1000

                generated = ""
                if data.get("choices"):
                    generated = data["choices"][0].get("text", "")

                span.set_attribute("vllm.success", True)
                span.set_attribute("vllm.latency_ms", latency_ms)

                return {
                    "generated_text": generated,
                    "model_version": data.get("model", model),
                    "latency_ms": latency_ms,
                }

            except httpx.TimeoutException:
                span.set_attribute("vllm.error", "timeout")
                raise TimeoutError(
                    f"vLLM endpoint {self.base_url} timed out "
                    f"after {self.timeout_seconds}s"
                )
            except Exception as e:
                span.set_attribute("vllm.error", str(e))
                span.set_attribute("vllm.error_type", type(e).__name__)
                raise

    async def check_endpoint_status(self) -> bool:
        """Health-check the vLLM server."""
        try:
            resp = await self._http.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _discover_model(self) -> str:
        """Query /v1/models to learn the served model name."""
        try:
            resp = await self._http.get(f"{self.base_url}/v1/models")
            resp.raise_for_status()
            models = resp.json().get("data", [])
            if models:
                self.model = models[0]["id"]
                return self.model
        except Exception:
            pass
        return "unknown"
