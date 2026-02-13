"""
FastAPI Application Entry Point.

This is the main entry point for the BFF backend application.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from modules.backend.api import health
from modules.backend.api.v1 import router as api_v1_router
from modules.backend.core.config import get_settings
from modules.backend.core.exception_handlers import register_exception_handlers
from modules.backend.core.logging import get_logger, setup_logging
from modules.backend.core.middleware import RequestContextMiddleware

logger = get_logger(__name__)

# Module-level app instance (lazy initialization)
_app: FastAPI | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    settings = get_settings()
    setup_logging(level=settings.app_log_level)
    logger.info(
        "Application starting",
        extra={"app_name": settings.app_name, "env": settings.app_env},
    )
    yield
    logger.info("Application shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Backend for Frontend Python Web Application",
        version="0.1.0",
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc" if settings.app_debug else None,
        lifespan=lifespan,
    )

    # Request context middleware (must be added first to wrap all requests)
    # Provides: request_id, timing, structured logging context
    app.add_middleware(RequestContextMiddleware)

    # CORS middleware
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Register exception handlers for standardized error responses
    register_exception_handlers(app)

    # Health endpoints (no prefix)
    app.include_router(health.router, tags=["health"])

    # API v1 endpoints
    app.include_router(api_v1_router, prefix="/api/v1")

    return app


def get_app() -> FastAPI:
    """
    Get the application instance (lazy initialization).

    This function creates the app on first call and caches it.
    Use this instead of importing `app` directly to avoid
    import-time configuration errors.
    """
    global _app
    if _app is None:
        _app = create_app()
    return _app


# For uvicorn: `uvicorn modules.backend.main:app`
# This property-like access ensures lazy initialization
def __getattr__(name: str) -> FastAPI:
    """Support lazy access to `app` for uvicorn compatibility."""
    if name == "app":
        return get_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
