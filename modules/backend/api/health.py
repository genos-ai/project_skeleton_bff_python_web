"""
Health Check Endpoints.

Provides liveness, readiness, and detailed health checks.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from modules.backend.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


def utc_now() -> datetime:
    """Return current UTC time as timezone-naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Liveness check.

    Returns 200 if the process is running.
    Used by process monitors.
    """
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness_check() -> dict[str, Any]:
    """
    Readiness check.

    Returns 200 if ready to serve traffic.
    Checks critical dependencies (database, Redis).
    Used by load balancers.
    """
    checks: dict[str, dict[str, Any]] = {}
    all_healthy = True

    # TODO: Add database check
    # TODO: Add Redis check

    status = "healthy" if all_healthy else "unhealthy"

    if not all_healthy:
        logger.warning("Readiness check failed", extra={"checks": checks})
        raise HTTPException(status_code=503, detail={"status": status, "checks": checks})

    return {
        "status": status,
        "checks": checks,
        "timestamp": utc_now().isoformat(),
    }


@router.get("/health/detailed")
async def detailed_health_check() -> dict[str, Any]:
    """
    Detailed health check.

    Returns status of each component.
    Should be protected by authentication in production.
    Used for debugging.
    """
    # TODO: Add authentication check
    # TODO: Add component-by-component status

    return {
        "status": "healthy",
        "checks": {
            "database": {"status": "not_configured"},
            "redis": {"status": "not_configured"},
        },
        "timestamp": utc_now().isoformat(),
    }
