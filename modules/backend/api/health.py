"""
Health Check Endpoints.

Provides liveness, readiness, and detailed health checks.

Endpoints:
- /health: Liveness check (process running)
- /health/ready: Readiness check (dependencies available)
- /health/detailed: Component-by-component status (for debugging)
"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now

router = APIRouter()
logger = get_logger(__name__)


async def check_database() -> dict[str, Any]:
    """
    Check database connectivity.

    Returns:
        Dict with status, latency, and optional error message
    """
    try:
        from modules.backend.core.config import get_app_config
        from modules.backend.core.database import get_db_session

        db_config = get_app_config().database

        if not db_config["host"] or not db_config["name"]:
            return {"status": "not_configured"}

        start = utc_now()
        async for session in get_db_session():
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
            break

        latency_ms = int((utc_now() - start).total_seconds() * 1000)

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
        }

    except ImportError:
        return {"status": "not_configured"}
    except Exception as e:
        logger.warning("Database health check failed", extra={"error": str(e)})
        return {
            "status": "unhealthy",
            "error": str(e),
        }


async def check_redis() -> dict[str, Any]:
    """
    Check Redis connectivity.

    Returns:
        Dict with status, latency, and optional error message
    """
    try:
        from modules.backend.core.config import get_redis_url
        import redis.asyncio as redis

        redis_url = get_redis_url()

        start = utc_now()
        client = redis.from_url(redis_url)
        await client.ping()
        await client.aclose()

        latency_ms = int((utc_now() - start).total_seconds() * 1000)

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
        }

    except ImportError:
        return {"status": "not_configured"}
    except Exception as e:
        logger.warning("Redis health check failed", extra={"error": str(e)})
        return {
            "status": "unhealthy",
            "error": str(e),
        }


@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Liveness check.

    Returns 200 if the process is running.
    No dependency checks - this endpoint should always respond quickly.
    Used by process monitors (e.g., Kubernetes liveness probe).
    """
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness_check() -> dict[str, Any]:
    """
    Readiness check.

    Returns 200 if ready to serve traffic.
    Checks critical dependencies (database, Redis) in parallel.
    Used by load balancers (e.g., Kubernetes readiness probe).

    Returns 503 if any critical dependency is unhealthy.
    """
    # Run checks in parallel for faster response
    db_check, redis_check = await asyncio.gather(
        check_database(),
        check_redis(),
        return_exceptions=True,
    )

    # Handle exceptions from gather
    if isinstance(db_check, Exception):
        db_check = {"status": "unhealthy", "error": str(db_check)}
    if isinstance(redis_check, Exception):
        redis_check = {"status": "unhealthy", "error": str(redis_check)}

    checks = {
        "database": db_check,
        "redis": redis_check,
    }

    # Determine overall status
    # "not_configured" is OK - the service can run without these if not needed
    # "unhealthy" means a configured dependency is down
    unhealthy_checks = [
        name for name, check in checks.items()
        if check.get("status") == "unhealthy"
    ]

    if unhealthy_checks:
        status = "unhealthy"
        logger.warning(
            "Readiness check failed",
            extra={"unhealthy": unhealthy_checks, "checks": checks},
        )
        raise HTTPException(
            status_code=503,
            detail={
                "status": status,
                "checks": checks,
                "timestamp": utc_now().isoformat(),
            },
        )

    return {
        "status": "healthy",
        "checks": checks,
        "timestamp": utc_now().isoformat(),
    }


@router.get("/health/detailed")
async def detailed_health_check() -> dict[str, Any]:
    """
    Detailed health check.

    Returns comprehensive status of each component.
    Includes latency measurements and configuration status.

    Note: Should be protected by authentication in production
    to avoid exposing infrastructure details.
    """
    # Run all checks in parallel
    db_check, redis_check = await asyncio.gather(
        check_database(),
        check_redis(),
        return_exceptions=True,
    )

    # Handle exceptions
    if isinstance(db_check, Exception):
        db_check = {"status": "error", "error": str(db_check)}
    if isinstance(redis_check, Exception):
        redis_check = {"status": "error", "error": str(redis_check)}

    checks = {
        "database": db_check,
        "redis": redis_check,
    }

    # Add application info
    try:
        from modules.backend.core.config import get_app_config
        app_config = get_app_config()
        app_settings = app_config.application

        app_info = {
            "name": app_settings["name"],
            "env": app_settings["environment"],
            "debug": app_settings["debug"],
            "version": app_settings["version"],
        }
    except Exception:
        app_info = {"status": "not_configured"}

    # Determine overall status
    statuses = [check.get("status") for check in checks.values()]
    if "unhealthy" in statuses or "error" in statuses:
        overall_status = "unhealthy"
    elif all(s == "not_configured" for s in statuses):
        overall_status = "healthy"  # No dependencies configured is OK
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "application": app_info,
        "checks": checks,
        "timestamp": utc_now().isoformat(),
    }
