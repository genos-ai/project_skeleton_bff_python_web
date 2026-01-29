"""
FastAPI Dependencies.

Shared dependencies for request handling.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.database import get_db_session
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

# Type alias for database session dependency
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_request_id(x_request_id: str | None = Header(None)) -> str:
    """
    Extract or generate request ID from headers.

    Used for request tracing and correlation.
    """
    import uuid

    return x_request_id or str(uuid.uuid4())


RequestId = Annotated[str, Depends(get_request_id)]


async def get_current_user() -> None:
    """
    Get current authenticated user.

    TODO: Implement authentication logic.
    """
    # Placeholder for authentication
    raise HTTPException(status_code=401, detail="Not authenticated")


# Add more dependencies as needed:
# - get_current_active_user
# - require_admin
# - require_permissions
