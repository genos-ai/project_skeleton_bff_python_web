"""
Handler Registration.

Collects all routers for inclusion in the aiogram dispatcher.
"""

from aiogram import Router

from modules.telegram.handlers.common import router as common_router
from modules.telegram.handlers.example import router as example_router


def get_all_routers() -> list[Router]:
    """
    Get all routers to include in the dispatcher.

    Returns:
        List of Router instances

    Usage:
        # In dispatcher setup
        for router in get_all_routers():
            dp.include_router(router)
    """
    return [
        common_router,
        example_router,
    ]
