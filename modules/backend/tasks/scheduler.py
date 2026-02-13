"""
Task Scheduler Configuration.

Configures the Taskiq scheduler for time-based task execution.
Uses LabelScheduleSource for static schedules defined in task decorators.

Usage:
    # Start scheduler process
    python example.py --action scheduler

    # Or directly with taskiq
    taskiq scheduler modules.backend.tasks.scheduler:scheduler

Important:
    Run only ONE scheduler instance. Multiple instances will cause
    duplicate task execution.
"""

from typing import TYPE_CHECKING

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from taskiq import TaskiqScheduler


def create_scheduler() -> "TaskiqScheduler":
    """
    Create and configure the Taskiq scheduler.

    Returns:
        Configured TaskiqScheduler instance
    """
    from taskiq import TaskiqScheduler
    from taskiq.schedule_sources import LabelScheduleSource

    from modules.backend.tasks.broker import get_broker

    broker = get_broker()

    # LabelScheduleSource reads schedule config from task decorators
    # e.g., @broker.task(schedule=[{"cron": "0 2 * * *"}])
    label_source = LabelScheduleSource(broker)

    scheduler = TaskiqScheduler(
        broker=broker,
        sources=[label_source],
    )

    logger.info("Taskiq scheduler configured with LabelScheduleSource")

    return scheduler


# Lazy scheduler initialization
_scheduler: "TaskiqScheduler | None" = None


def get_scheduler() -> "TaskiqScheduler":
    """
    Get the scheduler instance, creating it if necessary.

    Returns:
        Configured scheduler instance
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = create_scheduler()
    return _scheduler


# For direct access (e.g., taskiq scheduler command)
def __getattr__(name: str):
    """Lazy attribute access for scheduler."""
    if name == "scheduler":
        return get_scheduler()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
