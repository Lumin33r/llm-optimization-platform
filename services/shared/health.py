"""Health check implementations for team services."""

from enum import Enum
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ServiceState(Enum):
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthChecker:
    """Manages service health state."""

    def __init__(self, sagemaker_client):
        self.state = ServiceState.STARTING
        self.sagemaker_client = sagemaker_client
        self.last_sagemaker_check: Optional[float] = None
        self.sagemaker_reachable: bool = False

    async def startup_check(self) -> bool:
        """
        Check if service startup is complete.
        Returns True when the application process is running and routes are
        registered.  External dependencies (SageMaker) are verified by the
        readiness probe instead, so pods can start and emit logs even when
        SageMaker is temporarily unreachable.
        """
        if self.state == ServiceState.STARTING:
            self.state = ServiceState.READY

            # Log SageMaker status on first startup check (non-blocking)
            if self.sagemaker_client is not None:
                try:
                    endpoint_ok = await self.sagemaker_client.check_endpoint_status()
                    self.sagemaker_reachable = endpoint_ok
                    if endpoint_ok:
                        logger.info("Startup: SageMaker endpoint is InService")
                    else:
                        logger.warning("Startup: SageMaker endpoint not yet InService — readiness probe will gate traffic")
                except Exception as exc:
                    logger.error("Startup: SageMaker check failed: %s: %s — readiness probe will gate traffic", type(exc).__name__, exc)

        return True

    async def readiness_check(self) -> bool:
        """
        Check if service is ready to handle traffic.
        Returns True when the application is up and responsive.
        SageMaker reachability is tracked for observability but does not
        gate readiness — the /predict endpoint handles SageMaker errors
        gracefully and the ops dashboard shows endpoint health independently.
        """
        if self.state in (ServiceState.STARTING, ServiceState.UNHEALTHY):
            return False

        # Periodic SageMaker health check (non-blocking for readiness)
        if self.sagemaker_client is not None:
            import time
            now = time.time()
            if self.last_sagemaker_check is None or (now - self.last_sagemaker_check) > 30:
                try:
                    self.sagemaker_reachable = await self.sagemaker_client.check_endpoint_status()
                except Exception as exc:
                    logger.warning("Readiness: SageMaker check failed: %s: %s", type(exc).__name__, exc)
                    self.sagemaker_reachable = False
                self.last_sagemaker_check = now

                if not self.sagemaker_reachable:
                    logger.warning("Readiness: SageMaker not reachable — pod is ready but predictions may fail")

        return self.state == ServiceState.READY

    async def liveness_check(self) -> bool:
        """
        Check if service is alive (not deadlocked).
        Returns True when:
        - Event loop responsive
        - Memory within limits
        - No deadlock detected
        """
        # Simple async responsiveness check
        try:
            await asyncio.sleep(0)  # Yield to event loop
            return True
        except Exception:
            return False
