"""
Centralized Logging Configuration.

All modules must use this logging setup. Do not create standalone loggers.

Features:
- Structured JSON logging with structlog
- Source-based JSONL file output (web, cli, telegram, api, database, tasks, unknown)
- Console output for development
- Request context binding (request_id, frontend)

Usage:
    from modules.backend.core.logging import get_logger, setup_logging

    # Setup at application start
    setup_logging(level="INFO", format_type="json", enable_file_logging=True)

    # Get logger in modules
    logger = get_logger(__name__)
    logger.info("Message", extra={"key": "value"})

Log Files (when enabled):
    data/logs/web.jsonl      - Web frontend requests
    data/logs/cli.jsonl      - CLI operations
    data/logs/telegram.jsonl - Telegram bot interactions
    data/logs/api.jsonl      - Direct API calls (integrations)
    data/logs/database.jsonl - Database operations and queries
    data/logs/tasks.jsonl    - Background tasks and scheduled jobs
    data/logs/internal.jsonl - Internal service operations
    data/logs/unknown.jsonl  - Requests without source identification
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from structlog.typing import Processor

# Valid log sources - logs are routed to files based on these
LOG_SOURCES = {
    "web",       # Web frontend requests (browser)
    "cli",       # CLI operations
    "mobile",    # Mobile application
    "telegram",  # Telegram bot
    "api",       # Direct API integrations
    "database",  # Database operations
    "tasks",     # Background tasks
    "internal",  # Internal services
    "unknown",   # Unidentified source
}

# Module-level state
_file_handlers: dict[str, logging.Handler] = {}
_logs_dir: Path | None = None


def _get_project_root() -> Path:
    """Find project root by looking for .project_root marker."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".project_root").exists():
            return parent
    # Fallback to current working directory
    return Path.cwd()


def _get_logs_dir() -> Path:
    """Get the logs directory path, creating if needed."""
    global _logs_dir
    if _logs_dir is None:
        project_root = _get_project_root()
        _logs_dir = project_root / "data" / "logs"
        _logs_dir.mkdir(parents=True, exist_ok=True)
    return _logs_dir


def _create_file_handler(
    source: str,
    formatter: logging.Formatter,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> RotatingFileHandler:
    """
    Create a rotating file handler for a specific source.

    Args:
        source: Log source name (web, cli, telegram, etc.)
        formatter: Log formatter to use
        max_bytes: Max file size before rotation (default 10MB)
        backup_count: Number of backup files to keep (default 5)

    Returns:
        Configured RotatingFileHandler
    """
    logs_dir = _get_logs_dir()
    log_file = logs_dir / f"{source}.jsonl"

    handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    return handler


class SourceRoutingHandler(logging.Handler):
    """
    Handler that routes log records to source-specific file handlers.

    Routes based on:
    1. 'source' field in log record (explicit)
    2. 'frontend' field from request context
    3. Logger name patterns (e.g., 'modules.backend.tasks' -> tasks)
    4. Defaults to 'unknown'
    """

    def __init__(self, formatter: logging.Formatter, level: int = logging.DEBUG):
        super().__init__(level)
        self.formatter = formatter
        self._handlers: dict[str, logging.Handler] = {}
        self._initialize_handlers()

    def _initialize_handlers(self) -> None:
        """Create file handlers for each source."""
        for source in LOG_SOURCES:
            self._handlers[source] = _create_file_handler(source, self.formatter)

    def _determine_source(self, record: logging.LogRecord) -> str:
        """
        Determine the log source from the record.

        Priority:
        1. Explicit 'source' field
        2. 'frontend' field from request context
        3. Logger name pattern matching
        4. Default to 'unknown'
        """
        # Check for explicit source
        if hasattr(record, "source") and record.source in LOG_SOURCES:
            return record.source

        # Check for frontend from request context
        if hasattr(record, "frontend") and record.frontend in LOG_SOURCES:
            return record.frontend

        # Pattern matching on logger name
        logger_name = record.name.lower()

        if "task" in logger_name or "scheduler" in logger_name:
            return "tasks"
        if "database" in logger_name or "sqlalchemy" in logger_name:
            return "database"
        if "telegram" in logger_name:
            return "telegram"

        # Default
        return "unknown"

    def emit(self, record: logging.LogRecord) -> None:
        """Route the log record to the appropriate source handler."""
        try:
            source = self._determine_source(record)
            handler = self._handlers.get(source, self._handlers["unknown"])
            handler.emit(record)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close all source handlers."""
        for handler in self._handlers.values():
            handler.close()
        super().close()


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    enable_file_logging: bool = True,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Output format ('json' or 'console')
        enable_file_logging: Whether to write to JSONL files (default True)
    """
    # Convert string level to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors for both structlog and stdlib logging
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # JSON formatter for file output (always JSON for files)
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    if format_type == "console":
        # Human-readable console output for development
        structlog.configure(
            processors=shared_processors
            + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        console_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=True),
            foreign_pre_chain=shared_processors,
        )
    else:
        # JSON output for production
        structlog.configure(
            processors=shared_processors
            + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        console_formatter = json_formatter

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Add source-routing file handler
    if enable_file_logging:
        source_handler = SourceRoutingHandler(json_formatter, level=log_level)
        root_logger.addHandler(source_handler)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> Any:
    """
    Get a logger instance for the given name.

    Args:
        name: Logger name, typically __name__

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


def log_with_source(logger: Any, source: str, level: str, message: str, **kwargs: Any) -> None:
    """
    Log a message with an explicit source.

    Use this when you need to override the automatic source detection.

    Args:
        logger: The logger instance
        source: Log source (web, cli, telegram, api, database, tasks, internal)
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        **kwargs: Additional context fields

    Example:
        log_with_source(logger, "database", "warning", "Slow query detected", query_ms=150)
    """
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(message, source=source, **kwargs)
