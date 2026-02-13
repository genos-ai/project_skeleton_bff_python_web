"""
Background Tasks Package.

Provides Taskiq-based background task processing with Redis backend.

Two types of tasks:
1. On-demand tasks (modules.backend.tasks.example) - triggered by code
2. Scheduled tasks (modules.backend.tasks.scheduled) - triggered by time (cron)

Usage (with Redis - production):
    # Import and register tasks
    from modules.backend.tasks import get_broker, register_tasks, register_scheduled_tasks

    broker = get_broker()
    tasks = register_tasks()  # On-demand tasks
    scheduled = register_scheduled_tasks()  # Scheduled tasks

    # Dispatch a task (fire and forget)
    await tasks["send_notification"].kiq(user_id="123", message="Hello!")

    # Dispatch and wait for result
    task = await tasks["process_data"].kiq(data={"key": "value"})
    result = await task.wait_result(timeout=30)

Usage (without Redis - testing):
    # Import task functions directly (no broker required)
    from modules.backend.tasks.example import send_notification, process_data
    from modules.backend.tasks.scheduled import daily_cleanup

    # Call directly as async functions
    result = await send_notification(user_id="123", message="Hello!")

CLI Commands:
    # Start worker (executes tasks)
    python example.py --action worker

    # Start scheduler (sends scheduled tasks to worker)
    python example.py --action scheduler

    # Or directly with taskiq
    taskiq worker modules.backend.tasks.broker:broker
    taskiq scheduler modules.backend.tasks.scheduler:scheduler

Note:
    Tasks require Redis to be configured (REDIS_URL in environment).
    For testing without Redis, import task functions directly and call
    them as regular async functions.

Important:
    Run only ONE scheduler instance to avoid duplicate task execution.
"""

from modules.backend.tasks.broker import get_broker
from modules.backend.tasks.scheduler import get_scheduler
from modules.backend.tasks.example import (
    TASK_CONFIG,
    register_tasks,
    # Export raw functions for direct use/testing
    send_notification,
    process_data,
    cleanup_expired_records,
    generate_report,
)
from modules.backend.tasks.scheduled import (
    SCHEDULED_TASKS,
    register_scheduled_tasks,
    # Export raw functions for direct use/testing
    daily_cleanup,
    hourly_health_check,
    weekly_report_generation,
    metrics_aggregation,
)

__all__ = [
    # Broker and scheduler
    "get_broker",
    "get_scheduler",
    # Registration functions
    "register_tasks",
    "register_scheduled_tasks",
    # Configuration metadata
    "TASK_CONFIG",
    "SCHEDULED_TASKS",
    # On-demand task functions (can be called directly without Redis)
    "send_notification",
    "process_data",
    "cleanup_expired_records",
    "generate_report",
    # Scheduled task functions (can be called directly without Redis)
    "daily_cleanup",
    "hourly_health_check",
    "weekly_report_generation",
    "metrics_aggregation",
]


def __getattr__(name: str):
    """Lazy attribute access for broker and scheduler."""
    if name == "broker":
        return get_broker()
    if name == "scheduler":
        return get_scheduler()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
