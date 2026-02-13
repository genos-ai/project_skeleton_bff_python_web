"""
Example Background Tasks.

Demonstrates Taskiq task patterns for common use cases.
These serve as templates for implementing your own background tasks.

Usage:
    # From a service or endpoint
    from modules.backend.tasks.example import send_notification, process_data

    # Fire and forget (don't wait for result)
    await send_notification.kiq(user_id="123", message="Hello!")

    # Wait for result
    task = await process_data.kiq(data={"key": "value"})
    result = await task.wait_result(timeout=30)

Note:
    Task functions can be called directly for testing without Redis.
    The @broker.task decorator is applied lazily when the module is
    accessed through the tasks package with Redis configured.
"""

import asyncio
from typing import Any
from uuid import UUID

from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now

logger = get_logger(__name__)


async def send_notification(
    user_id: str,
    message: str,
    channel: str = "email",
) -> dict[str, Any]:
    """
    Send a notification to a user.

    This is an example task demonstrating:
    - Async execution
    - Retry on failure
    - Structured logging
    - Return value for tracking

    Args:
        user_id: Target user ID
        message: Notification message
        channel: Delivery channel (email, sms, push)

    Returns:
        Dict with delivery status and timestamp
    """
    logger.info(
        "Sending notification",
        extra={
            "user_id": user_id,
            "channel": channel,
            "message_length": len(message),
        },
    )

    # Simulate notification delivery
    # Replace with actual notification logic (email service, SMS gateway, etc.)
    await asyncio.sleep(0.1)

    # In a real implementation:
    # if channel == "email":
    #     await email_service.send(user_id, message)
    # elif channel == "sms":
    #     await sms_service.send(user_id, message)

    result = {
        "status": "delivered",
        "user_id": user_id,
        "channel": channel,
        "sent_at": utc_now().isoformat(),
    }

    logger.info(
        "Notification sent",
        extra={"user_id": user_id, "channel": channel, "status": "delivered"},
    )

    return result


async def process_data(
    data: dict[str, Any],
    operation: str = "transform",
) -> dict[str, Any]:
    """
    Process data in the background.

    This is an example task demonstrating:
    - Data processing patterns
    - Operation-based routing
    - Result tracking

    Args:
        data: Data payload to process
        operation: Type of processing (transform, validate, aggregate)

    Returns:
        Processed data with metadata
    """
    logger.info(
        "Processing data",
        extra={
            "operation": operation,
            "data_keys": list(data.keys()),
        },
    )

    started_at = utc_now()

    # Simulate processing
    # Replace with actual data processing logic
    await asyncio.sleep(0.1)

    # Example transformations
    if operation == "transform":
        processed = {k: str(v).upper() for k, v in data.items()}
    elif operation == "validate":
        processed = {"valid": True, "fields_checked": list(data.keys())}
    elif operation == "aggregate":
        processed = {"count": len(data), "keys": list(data.keys())}
    else:
        processed = data

    completed_at = utc_now()
    duration_ms = (completed_at - started_at).total_seconds() * 1000

    result = {
        "status": "completed",
        "operation": operation,
        "result": processed,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": duration_ms,
    }

    logger.info(
        "Data processing completed",
        extra={
            "operation": operation,
            "duration_ms": duration_ms,
        },
    )

    return result


async def cleanup_expired_records(
    table_name: str,
    older_than_days: int = 30,
) -> dict[str, Any]:
    """
    Cleanup expired records from a table.

    This is an example scheduled task demonstrating:
    - Maintenance operations
    - No retry (idempotent operation)
    - Audit logging

    Args:
        table_name: Name of table to clean
        older_than_days: Delete records older than this many days

    Returns:
        Cleanup statistics
    """
    logger.info(
        "Starting cleanup",
        extra={
            "table_name": table_name,
            "older_than_days": older_than_days,
        },
    )

    # In a real implementation:
    # async with get_session() as session:
    #     cutoff = utc_now() - timedelta(days=older_than_days)
    #     result = await session.execute(
    #         delete(Model).where(Model.created_at < cutoff)
    #     )
    #     deleted_count = result.rowcount
    #     await session.commit()

    # Simulate cleanup
    await asyncio.sleep(0.1)
    deleted_count = 0  # Placeholder

    result = {
        "status": "completed",
        "table_name": table_name,
        "deleted_count": deleted_count,
        "older_than_days": older_than_days,
        "completed_at": utc_now().isoformat(),
    }

    logger.info(
        "Cleanup completed",
        extra={
            "table_name": table_name,
            "deleted_count": deleted_count,
        },
    )

    return result


async def generate_report(
    report_type: str,
    parameters: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    """
    Generate a report in the background.

    This is an example long-running task demonstrating:
    - Report generation patterns
    - Progress tracking (via logging)
    - User notification on completion

    Args:
        report_type: Type of report to generate
        parameters: Report parameters (date range, filters, etc.)
        user_id: User who requested the report

    Returns:
        Report metadata and location
    """
    logger.info(
        "Starting report generation",
        extra={
            "report_type": report_type,
            "user_id": user_id,
            "parameters": parameters,
        },
    )

    # Simulate report generation phases
    # Phase 1: Gather data
    logger.debug("Report phase: gathering data")
    await asyncio.sleep(0.1)

    # Phase 2: Process data
    logger.debug("Report phase: processing data")
    await asyncio.sleep(0.1)

    # Phase 3: Generate output
    logger.debug("Report phase: generating output")
    await asyncio.sleep(0.1)

    # In a real implementation:
    # - Query database for report data
    # - Process and aggregate
    # - Generate PDF/CSV/Excel
    # - Store in file storage
    # - Notify user

    report_id = f"report_{report_type}_{utc_now().strftime('%Y%m%d_%H%M%S')}"

    result = {
        "status": "completed",
        "report_id": report_id,
        "report_type": report_type,
        "user_id": user_id,
        "file_path": f"/reports/{report_id}.pdf",  # Example path
        "generated_at": utc_now().isoformat(),
    }

    # Notify user that report is ready
    # await send_notification.kiq(
    #     user_id=user_id,
    #     message=f"Your {report_type} report is ready",
    #     channel="email",
    # )

    logger.info(
        "Report generation completed",
        extra={
            "report_id": report_id,
            "report_type": report_type,
            "user_id": user_id,
        },
    )

    return result


def register_tasks():
    """
    Register task functions with the Taskiq broker.

    This function wraps the plain async functions with broker.task decorators,
    enabling them to be dispatched as background tasks.

    Call this when Redis is available and you want to use the task queue.

    Returns:
        Dict mapping task names to registered task objects
    """
    from modules.backend.tasks.broker import get_broker

    broker = get_broker()

    # Register tasks with their configurations
    registered = {}

    registered["send_notification"] = broker.task(
        task_name="send_notification",
        retry_on_error=True,
        max_retries=3,
    )(send_notification)

    registered["process_data"] = broker.task(
        task_name="process_data",
        retry_on_error=True,
        max_retries=2,
    )(process_data)

    registered["cleanup_expired_records"] = broker.task(
        task_name="cleanup_expired_records",
        retry_on_error=False,
    )(cleanup_expired_records)

    registered["generate_report"] = broker.task(
        task_name="generate_report",
        retry_on_error=True,
        max_retries=1,
    )(generate_report)

    logger.info(
        "Tasks registered with broker",
        extra={"task_count": len(registered), "tasks": list(registered.keys())},
    )

    return registered


# Task configuration metadata (for documentation and testing)
TASK_CONFIG = {
    "send_notification": {
        "retry_on_error": True,
        "max_retries": 3,
        "description": "Send notifications to users via various channels",
    },
    "process_data": {
        "retry_on_error": True,
        "max_retries": 2,
        "description": "Process data with various operations (transform, validate, aggregate)",
    },
    "cleanup_expired_records": {
        "retry_on_error": False,
        "max_retries": 0,
        "description": "Clean up expired records from database tables",
    },
    "generate_report": {
        "retry_on_error": True,
        "max_retries": 1,
        "description": "Generate reports in the background",
    },
}
