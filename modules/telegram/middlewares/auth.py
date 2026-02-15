"""
Authentication Middleware.

User ID whitelisting for Telegram bot access control.
Telegram user IDs are immutable integers that cannot be spoofed within the Telegram API.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from modules.backend.core.config import get_settings
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

# User roles for authorization
USER_ROLES = {
    "admin": 3,    # Full access: kill switch, deploy, config changes
    "trader": 2,   # Trade access: buy/sell within limits
    "viewer": 1,   # Read-only: status commands only
}


class AuthMiddleware(BaseMiddleware):
    """
    Authentication middleware using Telegram user ID whitelisting.

    Checks if the user is in the authorized users list before processing.
    Silently drops unauthorized requests to avoid revealing bot existence.

    Configuration:
        Set TELEGRAM_AUTHORIZED_USERS in environment as comma-separated user IDs.
        Example: TELEGRAM_AUTHORIZED_USERS=123456789,987654321

    Usage:
        # In dispatcher setup
        dp.update.outer_middleware(AuthMiddleware())

        # In handlers, access user role via data
        @router.message(Command("admin_command"))
        async def admin_handler(message: Message, user_role: str):
            if user_role != "admin":
                await message.answer("Unauthorized")
                return
            # ... admin logic
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Process the middleware.

        Args:
            handler: Next handler in the chain
            event: Telegram event (Update)
            data: Handler data dict

        Returns:
            Handler result or None if unauthorized
        """
        settings = get_settings()

        # Extract user from the event
        user = None
        chat_type = None

        if isinstance(event, Update):
            if event.message:
                user = event.message.from_user
                chat_type = event.message.chat.type
            elif event.callback_query:
                user = event.callback_query.from_user
                chat_type = event.callback_query.message.chat.type if event.callback_query.message else None
            elif event.inline_query:
                user = event.inline_query.from_user

        if not user:
            # No user in event, allow (might be channel post, etc.)
            return await handler(event, data)

        user_id = user.id

        # Check if user is authorized
        authorized_users = settings.telegram_authorized_users

        # If no authorized users configured, allow all (development mode)
        if not authorized_users:
            logger.debug(
                "No authorized users configured, allowing all",
                extra={"user_id": user_id},
            )
            data["user_role"] = "admin"  # Default to admin in dev mode
            data["telegram_user"] = user
            return await handler(event, data)

        if user_id not in authorized_users:
            logger.warning(
                "Unauthorized Telegram access attempt",
                extra={
                    "user_id": user_id,
                    "username": user.username,
                    "chat_type": chat_type,
                },
            )
            # Silently drop - don't reveal bot exists to unauthorized users
            return None

        # User is authorized - determine role
        # Default implementation: first user in list is admin, rest are traders
        # Override this with a proper role mapping in production
        if user_id == authorized_users[0]:
            role = "admin"
        else:
            role = "trader"

        data["user_role"] = role
        data["telegram_user"] = user

        logger.debug(
            "Authorized Telegram user",
            extra={
                "user_id": user_id,
                "username": user.username,
                "role": role,
            },
        )

        return await handler(event, data)


def require_role(min_role: str):
    """
    Decorator to require a minimum role for a handler.

    Args:
        min_role: Minimum required role ("viewer", "trader", "admin")

    Usage:
        @router.message(Command("trade"))
        @require_role("trader")
        async def trade_handler(message: Message, user_role: str):
            # Only traders and admins can access this
            pass
    """
    min_level = USER_ROLES.get(min_role, 0)

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            user_role = kwargs.get("user_role", "viewer")
            user_level = USER_ROLES.get(user_role, 0)

            if user_level < min_level:
                # Get message from args (first positional arg is usually message)
                message = args[0] if args else kwargs.get("message")
                if message and hasattr(message, "answer"):
                    await message.answer("⛔ You don't have permission for this action.")
                return None

            return await func(*args, **kwargs)

        return wrapper

    return decorator
