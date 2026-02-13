"""
Scheduled Background Tasks.

Tasks that run on a schedule (cron-based).
These tasks are registered with the broker and include schedule metadata
that the TaskiqScheduler reads via LabelScheduleSource.

Schedule Format:
    schedule=[{"cron": "* * * * *", "args": [...], "kwargs": {...}}]

Cron Format:
    ┌───────────── minute (0-59)
    │ ┌───────────── hour (0-23)
    │ │ ┌───────────── day of month (1-31)
    │ │ │ ┌───────────── month (1-12)
    │ │ │ │ ┌───────────── day of week (0-6, Sun=0)
    │ │ │ │ │
    * * * * *

Examples:
    "0 2 * * *"     - Daily at 2:00 AM UTC
    "*/15 * * * *"  - Every 15 minutes
    "0 0 * * 0"     - Weekly on Sunday at midnight
    "0 6 1 * *"     - Monthly on 1st at 6:00 AM

Usage:
    # Import and register scheduled tasks
    from modules.backend.tasks.scheduled import register_scheduled_tasks
    register_scheduled_tasks()

    # Start scheduler
    python example.py --action scheduler
"""

from typing import Any

from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now

logger = get_logger(__name__)


# =============================================================================
# Scheduled Task Functions
# =============================================================================
# These are plain async functions. They get wrapped with broker.task()
# and schedule configuration when register_scheduled_tasks() is called.


async def daily_cleanup(older_than_days: int = 30) -> dict[str, Any]:
    """
    Clean up expired records from various tables.

    Runs daily at 2:00 AM UTC.

    Args:
        older_than_days: Delete records older than this many days

    Returns:
        Cleanup statistics
    """
    logger.info(
        "Starting daily cleanup",
        extra={"older_than_days": older_than_days},
    )

    # In a real implementation:
    # async with get_session() as session:
    #     # Clean expired sessions
    #     sessions_deleted = await cleanup_expired_sessions(session, older_than_days)
    #     # Clean old audit logs (beyond retention)
    #     logs_deleted = await cleanup_old_audit_logs(session, days=365*7)
    #     # Clean orphaned files
    #     files_deleted = await cleanup_orphaned_files(older_than_days)
    #     await session.commit()

    result = {
        "status": "completed",
        "older_than_days": older_than_days,
        "tables_cleaned": ["sessions", "audit_logs", "temp_files"],
        "completed_at": utc_now().isoformat(),
    }

    logger.info("Daily cleanup completed", extra=result)
    return result


async def hourly_health_check() -> dict[str, Any]:
    """
    Perform periodic health checks on external services.

    Runs every hour at minute 0.

    Returns:
        Health check results
    """
    logger.info("Starting hourly health check")

    # In a real implementation:
    # checks = {
    #     "database": await check_database_connection(),
    #     "redis": await check_redis_connection(),
    #     "external_api": await check_external_api(),
    # }

    checks = {
        "database": {"status": "healthy", "latency_ms": 5},
        "redis": {"status": "healthy", "latency_ms": 2},
        "external_api": {"status": "healthy", "latency_ms": 150},
    }

    all_healthy = all(c["status"] == "healthy" for c in checks.values())

    result = {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
        "checked_at": utc_now().isoformat(),
    }

    log_level = "info" if all_healthy else "warning"
    getattr(logger, log_level)("Hourly health check completed", extra=result)

    return result


async def weekly_report_generation() -> dict[str, Any]:
    """
    Generate weekly summary reports.

    Runs every Sunday at 6:00 AM UTC.

    Returns:
        Report generation status
    """
    logger.info("Starting weekly report generation")

    # In a real implementation:
    # reports = [
    #     await generate_usage_report(period="week"),
    #     await generate_error_summary(period="week"),
    #     await generate_performance_report(period="week"),
    # ]

    result = {
        "status": "completed",
        "reports_generated": [
            "usage_report",
            "error_summary",
            "performance_report",
        ],
        "generated_at": utc_now().isoformat(),
    }

    logger.info("Weekly report generation completed", extra=result)
    return result


async def metrics_aggregation(interval_minutes: int = 15) -> dict[str, Any]:
    """
    Aggregate metrics for monitoring dashboards.

    Runs every 15 minutes.

    Args:
        interval_minutes: Aggregation interval

    Returns:
        Aggregation status
    """
    logger.debug(
        "Starting metrics aggregation",
        extra={"interval_minutes": interval_minutes},
    )

    # In a real implementation:
    # await aggregate_request_metrics(interval_minutes)
    # await aggregate_error_rates(interval_minutes)
    # await aggregate_response_times(interval_minutes)

    result = {
        "status": "completed",
        "interval_minutes": interval_minutes,
        "metrics_aggregated": [
            "request_count",
            "error_rate",
            "response_time_p50",
            "response_time_p95",
            "response_time_p99",
        ],
        "aggregated_at": utc_now().isoformat(),
    }

    logger.debug("Metrics aggregation completed", extra=result)
    return result


# =============================================================================
# Schedule Configuration
# =============================================================================

SCHEDULED_TASKS = {
    "daily_cleanup": {
        "function": daily_cleanup,
        "schedule": [{"cron": "0 2 * * *", "kwargs": {"older_than_days": 30}}],
        "retry_on_error": False,  # Scheduled tasks typically don't retry
        "description": "Clean up expired records daily at 2:00 AM UTC",
    },
    "hourly_health_check": {
        "function": hourly_health_check,
        "schedule": [{"cron": "0 * * * *"}],  # Every hour at minute 0
        "retry_on_error": False,
        "description": "Check external service health every hour",
    },
    "weekly_report_generation": {
        "function": weekly_report_generation,
        "schedule": [{"cron": "0 6 * * 0"}],  # Sunday at 6:00 AM UTC
        "retry_on_error": True,
        "max_retries": 2,
        "description": "Generate weekly summary reports on Sunday",
    },
    "metrics_aggregation": {
        "function": metrics_aggregation,
        "schedule": [{"cron": "*/15 * * * *", "kwargs": {"interval_minutes": 15}}],
        "retry_on_error": False,
        "description": "Aggregate metrics every 15 minutes",
    },
}


def register_scheduled_tasks() -> dict[str, Any]:
    """
    Register scheduled task functions with the Taskiq broker.

    This wraps the plain async functions with broker.task decorators
    including their schedule configuration.

    Returns:
        Dict mapping task names to registered task objects
    """
    from modules.backend.tasks.broker import get_broker

    broker = get_broker()
    registered = {}

    for task_name, config in SCHEDULED_TASKS.items():
        task_kwargs = {
            "task_name": task_name,
            "schedule": config["schedule"],
            "retry_on_error": config.get("retry_on_error", False),
        }

        if "max_retries" in config:
            task_kwargs["max_retries"] = config["max_retries"]

        registered[task_name] = broker.task(**task_kwargs)(config["function"])

    logger.info(
        "Scheduled tasks registered",
        extra={
            "task_count": len(registered),
            "tasks": list(registered.keys()),
        },
    )

    return registered
