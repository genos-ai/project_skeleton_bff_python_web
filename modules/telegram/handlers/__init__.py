"""Telegram Bot Handlers — re-exports."""

from modules.telegram.handlers.common import router as common_router
from modules.telegram.handlers.example import router as example_router
from modules.telegram.handlers.setup import get_all_routers

__all__ = [
    "common_router",
    "example_router",
    "get_all_routers",
]
