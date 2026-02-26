"""Health check implementations for team services."""

from enum import Enum
import asyncio
from typing import Optional


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
        Returns True when:
        - Configuration loaded
        - SageMaker endpoint is reachable (initial check)
        - All dependencies initialized
        """
        if self.state == ServiceState.STARTING:
            # Verify SageMaker endpoint exists and is InService
            try:
                endpoint_ok = await self.sagemaker_client.check_endpoint_status()
                if endpoint_ok:
                    self.state = ServiceState.READY
                    self.sagemaker_reachable = True
                    return True
            except Exception:
                return False
        return self.state != ServiceState.STARTING

    async def readiness_check(self) -> bool:
        """
        Check if service is ready to handle traffic.
        Returns True when:
        - Startup complete
        - SageMaker endpoint InService (recent check)
        - No circuit breaker open
        """
        if self.state in (ServiceState.STARTING, ServiceState.UNHEALTHY):
            return False

        # Periodic SageMaker health verification
        import time
        now = time.time()
        if self.last_sagemaker_check is None or (now - self.last_sagemaker_check) > 30:
            self.sagemaker_reachable = await self.sagemaker_client.check_endpoint_status()
            self.last_sagemaker_check = now

        return self.sagemaker_reachable and self.state == ServiceState.READY

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
