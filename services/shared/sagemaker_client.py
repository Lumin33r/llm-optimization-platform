"""SageMaker endpoint client with OTEL tracing."""

import os
import json
import asyncio
from typing import Optional, Dict, Any
import boto3
from botocore.config import Config
from opentelemetry import trace


class SageMakerClient:
    """Async SageMaker endpoint client with timeout and error handling."""

    def __init__(
        self,
        endpoint_name: str,
        timeout_ms: int = 30000,
        enable_fallback: bool = False,
        fallback_response: Optional[Dict] = None
    ):
        self.endpoint_name = endpoint_name
        self.timeout_seconds = timeout_ms / 1000
        self.enable_fallback = enable_fallback
        self.fallback_response = fallback_response or {"error": "fallback_response"}

        # Configure boto3 with timeout
        config = Config(
            read_timeout=self.timeout_seconds,
            connect_timeout=5,
            retries={'max_attempts': 1}
        )
        self.sagemaker_runtime = boto3.client(
            'sagemaker-runtime',
            region_name=os.getenv('AWS_REGION', 'us-west-2'),
            config=config
        )
        self.sagemaker = boto3.client('sagemaker')
        self.tracer = trace.get_tracer(__name__)

    async def check_endpoint_status(self) -> bool:
        """Check if SageMaker endpoint is InService."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.sagemaker.describe_endpoint(EndpointName=self.endpoint_name)
            )
            return response['EndpointStatus'] == 'InService'
        except Exception:
            return False

    async def invoke(
        self,
        payload: Dict[str, Any],
        correlation_id: str,
        variant: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke SageMaker endpoint with tracing.

        Args:
            payload: Request payload (will be JSON serialized)
            correlation_id: Request correlation ID for tracing
            variant: Optional production variant name (for A/B testing)

        Returns:
            Parsed JSON response from model

        Raises:
            TimeoutError: If request exceeds timeout_ms
            SageMakerError: If SageMaker returns an error
        """
        with self.tracer.start_as_current_span("sagemaker.invoke_endpoint") as span:
            span.set_attribute("sagemaker.endpoint", self.endpoint_name)
            span.set_attribute("correlation_id", correlation_id)
            if variant:
                span.set_attribute("sagemaker.variant", variant)

            try:
                loop = asyncio.get_event_loop()

                invoke_params = {
                    'EndpointName': self.endpoint_name,
                    'Body': json.dumps(payload),
                    'ContentType': 'application/json',
                    'Accept': 'application/json'
                }

                if variant:
                    invoke_params['TargetVariant'] = variant

                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self.sagemaker_runtime.invoke_endpoint(**invoke_params)
                    ),
                    timeout=self.timeout_seconds
                )

                result = json.loads(response['Body'].read().decode())
                span.set_attribute("sagemaker.success", True)
                return result

            except asyncio.TimeoutError:
                span.set_attribute("sagemaker.error", "timeout")
                span.set_attribute("sagemaker.timeout_ms", self.timeout_seconds * 1000)

                if self.enable_fallback:
                    span.set_attribute("sagemaker.fallback_used", True)
                    return self.fallback_response
                else:
                    raise TimeoutError(
                        f"SageMaker endpoint {self.endpoint_name} timed out "
                        f"after {self.timeout_seconds}s"
                    )

            except Exception as e:
                span.set_attribute("sagemaker.error", str(e))
                span.set_attribute("sagemaker.error_type", type(e).__name__)
                raise


class SageMakerError(Exception):
    """SageMaker invocation error."""
    pass
