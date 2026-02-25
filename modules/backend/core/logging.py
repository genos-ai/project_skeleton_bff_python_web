"""
Centralized Logging Configuration.

All modules must use this logging setup. Do not create standalone loggers.
Configuration is loaded from config/settings/logging.yaml.

Features:
- Structured JSON logging with structlog
- Source-based JSONL file output (web, cli, telegram, api, database, tasks, unknown)
- Console output for development
- Request context binding (request_id, frontend)
- Configuration driven by logging.yaml

Usage:
    from modules.backend.core.logging import get_logger, setup_logging

    # Setup at application start (loads from logging.yaml)
    setup_logging()

    # Override config values if needed
    setup_logging(level="DEBUG", format_type="console")

    # Get logger in modules
    logger = get_logger(__name__)
    logger.info("Message", extra={"key": "value"})

Log Files (when enabled via logging.yaml):
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
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from structlog.typing import Processor

from modules.backend.core.config import find_project_root, load_yaml_config

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
_logging_config: dict[str, Any] | None = None


def _load_logging_config() -> dict[str, Any]:
    """
    Load logging configuration from config/settings/logging.yaml.

    Returns:
        Dictionary containing logging configuration

    Raises:
        FileNotFoundError: If logging.yaml does not exist
    """
    global _logging_config
    if _logging_config is None:
        _logging_config = load_yaml_config("logging.yaml")
    return _logging_config


def _get_logging_config() -> dict[str, Any]:
    """
    Get the cached logging configuration.

    Returns:
        Dictionary containing logging configuration
    """
    return _load_logging_config()


def _get_logs_dir() -> Path:
    """Get the logs directory path, creating if needed."""
    global _logs_dir
    if _logs_dir is None:
        project_root = find_project_root()
        _logs_dir = project_root / "data" / "logs"
        _logs_dir.mkdir(parents=True, exist_ok=True)
    return _logs_dir


def _create_file_handler(
    source: str,
    formatter: logging.Formatter,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> RotatingFileHandler:
    """
    Create a rotating file handler for a specific source.

    Args:
        source: Log source name (web, cli, telegram, etc.)
        formatter: Log formatter to use
        max_bytes: Max file size before rotation (from config if not provided)
        backup_count: Number of backup files to keep (from config if not provided)

    Returns:
        Configured RotatingFileHandler
    """
    config = _get_logging_config()
    file_config = config["handlers"]["file"]

    if max_bytes is None:
        max_bytes = file_config["max_bytes"]
    if backup_count is None:
        backup_count = file_config["backup_count"]

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
    level: str | None = None,
    format_type: str | None = None,
    enable_console: bool | None = None,
    enable_file_logging: bool | None = None,
) -> None:
    """
    Configure structured logging for the application.

    Configuration is loaded from config/settings/logging.yaml.
    Parameters passed to this function override the YAML configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Overrides config.
        format_type: Output format ('json' or 'console'). Overrides config.
        enable_console: Whether to enable console output. Overrides config.
        enable_file_logging: Whether to write to JSONL files. Overrides config.
    """
    config = _get_logging_config()

    effective_level = level if level is not None else config["level"]
    effective_format = format_type if format_type is not None else config["format"]

    handlers_config = config["handlers"]
    console_config = handlers_config["console"]
    file_config = handlers_config["file"]

    effective_console_enabled = (
        enable_console if enable_console is not None
        else console_config["enabled"]
    )
    effective_file_enabled = (
        enable_file_logging if enable_file_logging is not None
        else file_config["enabled"]
    )

    log_level = getattr(logging, effective_level.upper())

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

    if effective_format == "console":
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

    # Add console handler if enabled
    if effective_console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Add source-routing file handler if enabled
    if effective_file_enabled:
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
