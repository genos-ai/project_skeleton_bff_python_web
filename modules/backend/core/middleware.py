"""
Request Context Middleware.

Middleware for request tracking, timing, frontend identification, and context propagation.
"""

import uuid
from datetime import datetime, timezone

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

# Valid frontend identifiers
# Add new frontends here as they are developed
# Note: These should align with LOG_SOURCES in logging.py for proper log routing
KNOWN_FRONTENDS = {"web", "cli", "mobile", "telegram", "api", "internal"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds request context to every request.

    Features:
    - Generates or propagates request ID (X-Request-ID header)
    - Extracts frontend identifier (X-Frontend-ID header)
    - Records request timing (X-Response-Time header)
    - Binds request context to structlog for automatic inclusion in logs
    - Stores context in request.state for access by handlers

    Headers:
    - X-Request-ID: Unique request identifier (generated if not provided)
    - X-Frontend-ID: Frontend source identifier (web, cli, mobile, api, internal)
    - X-Response-Time: Response duration in milliseconds

    Usage:
        All logs within a request will automatically include:
        - request_id: Unique identifier for the request
        - frontend: Source frontend identifier
        - method: HTTP method
        - path: Request path

        Access in endpoints:
            request.state.request_id
            request.state.frontend
            request.state.start_time
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request with context tracking."""
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Extract frontend identifier
        # Default to "unknown" if not provided or not recognized
        frontend = request.headers.get("X-Frontend-ID", "unknown").lower()
        if frontend not in KNOWN_FRONTENDS:
            frontend = "unknown"

        # Record start time (timezone-naive UTC)
        start_time = datetime.now(timezone.utc).replace(tzinfo=None)

        # Store in request state for access by handlers
        request.state.request_id = request_id
        request.state.frontend = frontend
        request.state.start_time = start_time

        # Bind context to structlog - all logs in this request will include these
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            frontend=frontend,
            method=request.method,
            path=request.url.path,
        )

        # Log request start (debug level to avoid noise)
        logger.debug(
            "Request started",
            extra={
                "client_host": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent"),
            },
        )

        try:
            # Process the request
            response = await call_next(request)

            # Calculate response time
            end_time = datetime.now(timezone.utc).replace(tzinfo=None)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Add response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms}ms"

            # Log request completion
            logger.debug(
                "Request completed",
                extra={
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

            return response

        except Exception as exc:
            # Calculate duration even on error
            end_time = datetime.now(timezone.utc).replace(tzinfo=None)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Log the error (exception handlers will handle the response)
            logger.error(
                "Request failed with exception",
                extra={
                    "duration_ms": duration_ms,
                    "error_type": type(exc).__name__,
                },
            )

            # Re-raise to let exception handlers process it
            raise

        finally:
            # Clear context vars to prevent leaking to other requests
            structlog.contextvars.clear_contextvars()
