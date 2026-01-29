"""
API Version 1 Router.

Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

# Import endpoint routers here as they are created
# from modules.backend.api.v1.endpoints import users, projects

router = APIRouter()

# Include endpoint routers here as they are created
# router.include_router(users.router, prefix="/users", tags=["users"])
# router.include_router(projects.router, prefix="/projects", tags=["projects"])
