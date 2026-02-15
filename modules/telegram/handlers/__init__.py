"""
Telegram Bot Handlers.

Command and message handlers organized by feature.

Handler Organization:
- common.py: Universal commands (/start, /help, /cancel)
- example.py: Example handlers demonstrating patterns

Adding New Handlers:
1. Create a new file in this directory
2. Create a Router and add handlers
3. Import and add to get_all_routers()
"""

from aiogram import Router

from modules.telegram.handlers.common import router as common_router
from modules.telegram.handlers.example import router as example_router

__all__ = [
    "get_all_routers",
    "common_router",
    "example_router",
]


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
