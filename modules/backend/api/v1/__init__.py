"""
API Version 1 Router.

Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from modules.backend.api.v1.endpoints import notes

router = APIRouter()

# Notes endpoints
router.include_router(notes.router, prefix="/notes", tags=["notes"])

# Add more endpoint routers here as they are created:
# from modules.backend.api.v1.endpoints import users
# router.include_router(users.router, prefix="/users", tags=["users"])
