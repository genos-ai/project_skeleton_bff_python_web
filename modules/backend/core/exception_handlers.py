"""
Exception Handlers.

FastAPI exception handlers that convert application exceptions
to standardized API responses. All exceptions are logged and
returned in the standard ErrorResponse format.

Usage:
    from modules.backend.core.exception_handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from modules.backend.core.exceptions import (
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DatabaseError,
    ExternalServiceError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from modules.backend.core.logging import get_logger
from modules.backend.schemas.base import ErrorDetail, ErrorResponse, ResponseMetadata

logger = get_logger(__name__)

# Map exception types to HTTP status codes
EXCEPTION_STATUS_MAP: dict[type[ApplicationError], int] = {
    NotFoundError: 404,
    ValidationError: 400,
    AuthenticationError: 401,
    AuthorizationError: 403,
    ConflictError: 409,
    RateLimitError: 429,
    ExternalServiceError: 502,
    DatabaseError: 503,
}


def _get_request_id(request: Request) -> str | None:
    """Extract request ID from request state or headers."""
    # Try request state first (set by middleware/dependency)
    if hasattr(request.state, "request_id"):
        return request.state.request_id
    # Fall back to header
    return request.headers.get("x-request-id")


async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    """
    Handle all ApplicationError subclasses.

    Converts application exceptions to standardized JSON responses
    with appropriate HTTP status codes.
    """
    status_code = EXCEPTION_STATUS_MAP.get(type(exc), 500)
    request_id = _get_request_id(request)

    # Log based on severity
    log_extra = {
        "code": exc.code,
        "message": exc.message,
        "status": status_code,
        "path": request.url.path,
        "method": request.method,
    }
    if request_id:
        log_extra["request_id"] = request_id

    if status_code >= 500:
        logger.error("Server error", extra=log_extra)
    else:
        logger.warning("Client error", extra=log_extra)

    # Build error detail
    error_detail = ErrorDetail(code=exc.code, message=exc.message)

    # Include validation details if present
    if isinstance(exc, ValidationError) and exc.details:
        error_detail.details = exc.details

    # Build response with metadata
    metadata = ResponseMetadata(request_id=request_id)
    response = ErrorResponse(error=error_detail, metadata=metadata)

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Handle FastAPI/Pydantic request validation errors.

    Converts validation errors to standardized format matching
    our ErrorResponse schema.
    """
    request_id = _get_request_id(request)

    # Extract validation error details
    errors = exc.errors()
    details = {
        "validation_errors": [
            {
                "field": ".".join(str(loc) for loc in err.get("loc", [])),
                "message": err.get("msg", "Validation error"),
                "type": err.get("type", "unknown"),
            }
            for err in errors
        ]
    }

    logger.warning(
        "Request validation failed",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error_count": len(errors),
            "request_id": request_id,
        },
    )

    error_detail = ErrorDetail(
        code="VAL_REQUEST_INVALID",
        message="Request validation failed",
        details=details,
    )

    metadata = ResponseMetadata(request_id=request_id)
    response = ErrorResponse(error=error_detail, metadata=metadata)

    return JSONResponse(
        status_code=422,
        content=response.model_dump(mode="json"),
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Handle unexpected exceptions.

    Catches all unhandled exceptions and returns a generic error
    response. In production, details are hidden for security.
    """
    request_id = _get_request_id(request)

    # Always log the full exception for debugging
    logger.exception(
        "Unhandled exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
            "request_id": request_id,
        },
    )

    # Return generic error (don't expose internal details)
    error_detail = ErrorDetail(
        code="SYS_INTERNAL_ERROR",
        message="An unexpected error occurred",
    )

    metadata = ResponseMetadata(request_id=request_id)
    response = ErrorResponse(error=error_detail, metadata=metadata)

    return JSONResponse(
        status_code=500,
        content=response.model_dump(mode="json"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers with the FastAPI app.

    Call this function after creating the FastAPI app instance
    to enable standardized error handling.

    Args:
        app: FastAPI application instance
    """
    # Handle all application-specific exceptions
    app.add_exception_handler(ApplicationError, application_error_handler)

    # Handle request validation errors (malformed requests)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    # Catch-all for unexpected exceptions
    app.add_exception_handler(Exception, unhandled_exception_handler)

    logger.debug("Exception handlers registered")
