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

        if not db_config.host or not db_config.name:
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
    Checks critical dependencies in parallel using TaskGroup.
    Returns 503 if any critical dependency is unhealthy.
    """
    from modules.backend.core.config import get_app_config
    timeout = get_app_config().observability.health_checks.ready_timeout_seconds

    db_result: dict[str, Any] = {"status": "error", "error": "check did not run"}
    redis_result: dict[str, Any] = {"status": "error", "error": "check did not run"}

    try:
        async with asyncio.timeout(timeout):
            async with asyncio.TaskGroup() as tg:
                db_task = tg.create_task(check_database())
                redis_task = tg.create_task(check_redis())
            db_result = db_task.result()
            redis_result = redis_task.result()
    except* Exception as eg:
        for exc in eg.exceptions:
            logger.warning("Health check task failed", extra={"error": str(exc)})

    checks = {
        "database": db_result,
        "redis": redis_result,
    }

    unhealthy_checks = [
        name for name, check in checks.items()
        if check.get("status") == "unhealthy"
    ]

    if unhealthy_checks:
        logger.warning(
            "Readiness check failed",
            extra={"unhealthy": unhealthy_checks, "checks": checks},
        )
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
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

    Returns comprehensive status including dependency checks and pool metrics.
    Should be protected by authentication in production
    (controlled by observability.yaml health_checks.detailed_auth_required).
    """
    db_result: dict[str, Any] = {"status": "error", "error": "check did not run"}
    redis_result: dict[str, Any] = {"status": "error", "error": "check did not run"}

    try:
        async with asyncio.TaskGroup() as tg:
            db_task = tg.create_task(check_database())
            redis_task = tg.create_task(check_redis())
        db_result = db_task.result()
        redis_result = redis_task.result()
    except* Exception as eg:
        for exc in eg.exceptions:
            logger.warning("Detailed health check task failed", extra={"error": str(exc)})

    checks = {
        "database": db_result,
        "redis": redis_result,
    }

    try:
        from modules.backend.core.config import get_app_config
        app_config = get_app_config()
        app_settings = app_config.application

        app_info = {
            "name": app_settings.name,
            "env": app_settings.environment,
            "debug": app_settings.debug,
            "version": app_settings.version,
        }
    except Exception:
        app_info = {"status": "not_configured"}

    pools = _get_pool_status()

    statuses = [check.get("status") for check in checks.values()]
    if "unhealthy" in statuses or "error" in statuses:
        overall_status = "unhealthy"
    elif all(s == "not_configured" for s in statuses):
        overall_status = "healthy"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "application": app_info,
        "checks": checks,
        "pools": pools,
        "timestamp": utc_now().isoformat(),
    }


def _get_pool_status() -> dict[str, Any]:
    """Collect current pool and semaphore metrics for health reporting."""
    from modules.backend.core.concurrency import (
        _io_pool, _cpu_pool, _semaphores, _semaphore_capacities,
    )

    pools: dict[str, Any] = {}

    if _io_pool is not None:
        pools["thread_pool"] = {
            "max_workers": _io_pool._max_workers,
        }

    if _cpu_pool is not None:
        pools["process_pool"] = {
            "max_workers": _cpu_pool._max_workers,
        }

    if _semaphores:
        sem_status = {}
        for name, sem in _semaphores.items():
            sem_status[name] = {
                "capacity": _semaphore_capacities.get(name, "unknown"),
                "available": sem._value,
            }
        pools["semaphores"] = sem_status

    return pools
