"""
Unit tests for Telegram bot middlewares.

Tests authentication, rate limiting, and logging middlewares.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Update


class TestAuthMiddleware:
    """Tests for AuthMiddleware."""

    def _create_mock_update(self, user_id: int, username: str) -> MagicMock:
        """Create a mock Update object that passes isinstance checks."""
        user = MagicMock()
        user.id = user_id
        user.username = username

        message = MagicMock()
        message.from_user = user
        message.chat.type = "private"

        # Create a proper mock that will pass isinstance(event, Update)
        event = MagicMock(spec=Update)
        event.message = message
        event.callback_query = None
        event.inline_query = None

        return event

    @pytest.mark.asyncio
    async def test_allows_authorized_user(self):
        """Test that authorized users are allowed through."""
        from modules.telegram.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()
        handler = AsyncMock(return_value="result")

        event = self._create_mock_update(123456789, "testuser")

        mock_settings = MagicMock()
        mock_settings.telegram_authorized_users = [123456789, 987654321]

        with patch(
            "modules.telegram.middlewares.auth.get_settings",
            return_value=mock_settings,
        ):
            result = await middleware(handler, event, {})

        assert result == "result"
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_blocks_unauthorized_user(self):
        """Test that unauthorized users are blocked."""
        from modules.telegram.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()
        handler = AsyncMock(return_value="result")

        event = self._create_mock_update(999999999, "unauthorized")

        mock_settings = MagicMock()
        mock_settings.telegram_authorized_users = [123456789]

        with patch(
            "modules.telegram.middlewares.auth.get_settings",
            return_value=mock_settings,
        ):
            result = await middleware(handler, event, {})

        assert result is None
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_all_when_no_authorized_users(self):
        """Test that all users are allowed when no whitelist is configured."""
        from modules.telegram.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()
        handler = AsyncMock(return_value="result")

        event = self._create_mock_update(123456789, "anyuser")

        mock_settings = MagicMock()
        mock_settings.telegram_authorized_users = []

        with patch(
            "modules.telegram.middlewares.auth.get_settings",
            return_value=mock_settings,
        ):
            result = await middleware(handler, event, {})

        assert result == "result"
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_first_user_is_admin(self):
        """Test that the first authorized user gets admin role."""
        from modules.telegram.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()
        handler = AsyncMock(return_value="result")
        data = {}

        event = self._create_mock_update(123456789, "admin")

        mock_settings = MagicMock()
        mock_settings.telegram_authorized_users = [123456789, 987654321]

        with patch(
            "modules.telegram.middlewares.auth.get_settings",
            return_value=mock_settings,
        ):
            await middleware(handler, event, data)

        assert data["user_role"] == "admin"

    @pytest.mark.asyncio
    async def test_non_first_user_is_trader(self):
        """Test that non-first authorized users get trader role."""
        from modules.telegram.middlewares.auth import AuthMiddleware

        middleware = AuthMiddleware()
        handler = AsyncMock(return_value="result")
        data = {}

        event = self._create_mock_update(987654321, "trader")

        mock_settings = MagicMock()
        mock_settings.telegram_authorized_users = [123456789, 987654321]

        with patch(
            "modules.telegram.middlewares.auth.get_settings",
            return_value=mock_settings,
        ):
            await middleware(handler, event, data)

        assert data["user_role"] == "trader"


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    def _create_mock_message(self, user_id: int) -> MagicMock:
        """Create a mock Message object."""
        from aiogram.types import Message

        message = MagicMock(spec=Message)
        message.from_user = MagicMock(id=user_id)
        message.answer = AsyncMock()
        return message

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self):
        """Test that requests under the rate limit are allowed."""
        from modules.telegram.middlewares.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(rate_limit=10, rate_window=60)
        handler = AsyncMock(return_value="result")

        message = self._create_mock_message(123)

        result = await middleware(handler, message, {})

        assert result == "result"
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_blocks_requests_over_limit(self):
        """Test that requests over the rate limit are blocked."""
        from modules.telegram.middlewares.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(rate_limit=2, rate_window=60)
        handler = AsyncMock(return_value="result")

        message = self._create_mock_message(123)

        # Make requests up to the limit
        await middleware(handler, message, {})
        await middleware(handler, message, {})

        # This should be blocked
        result = await middleware(handler, message, {})

        assert result is None
        assert handler.call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_resets_after_window(self):
        """Test that rate limit resets after the time window."""
        from modules.telegram.middlewares.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(rate_limit=1, rate_window=1)
        handler = AsyncMock(return_value="result")

        message = self._create_mock_message(123)

        # First request allowed
        await middleware(handler, message, {})

        # Second request blocked
        result = await middleware(handler, message, {})
        assert result is None

        # Wait for window to expire
        time.sleep(1.1)

        # Third request should be allowed
        result = await middleware(handler, message, {})
        assert result == "result"

    @pytest.mark.asyncio
    async def test_separate_limits_per_user(self):
        """Test that rate limits are tracked per user."""
        from modules.telegram.middlewares.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(rate_limit=1, rate_window=60)
        handler = AsyncMock(return_value="result")

        message1 = self._create_mock_message(123)
        message2 = self._create_mock_message(456)

        # User 1 makes a request
        await middleware(handler, message1, {})

        # User 2 should still be allowed
        result = await middleware(handler, message2, {})
        assert result == "result"


class TestLoggingMiddleware:
    """Tests for LoggingMiddleware."""

    def _create_mock_update(self, user_id: int, username: str, text: str = "/start") -> MagicMock:
        """Create a mock Update object."""
        from aiogram.types import Update

        user = MagicMock()
        user.id = user_id
        user.username = username

        message = MagicMock()
        message.from_user = user
        message.chat.id = 456
        message.chat.type = "private"
        message.text = text

        event = MagicMock(spec=Update)
        event.update_id = 789
        event.event_type = "message"
        event.message = message
        event.callback_query = None
        event.inline_query = None

        return event

    @pytest.mark.asyncio
    async def test_logs_update_context(self):
        """Test that logging middleware extracts and logs context."""
        from modules.telegram.middlewares.logging import LoggingMiddleware

        middleware = LoggingMiddleware()
        handler = AsyncMock(return_value="result")

        event = self._create_mock_update(123, "testuser")

        result = await middleware(handler, event, {})

        assert result == "result"
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_logs_errors(self):
        """Test that errors are logged."""
        from modules.telegram.middlewares.logging import LoggingMiddleware

        middleware = LoggingMiddleware()
        handler = AsyncMock(side_effect=ValueError("test error"))

        event = self._create_mock_update(123, "testuser")

        with pytest.raises(ValueError, match="test error"):
            await middleware(handler, event, {})


class TestUserRoles:
    """Tests for user role definitions."""

    def test_user_roles_hierarchy(self):
        """Test that user roles have correct hierarchy."""
        from modules.telegram.middlewares.auth import USER_ROLES

        assert USER_ROLES["viewer"] < USER_ROLES["trader"]
        assert USER_ROLES["trader"] < USER_ROLES["admin"]

    def test_all_roles_defined(self):
        """Test that all expected roles are defined."""
        from modules.telegram.middlewares.auth import USER_ROLES

        assert "viewer" in USER_ROLES
        assert "trader" in USER_ROLES
        assert "admin" in USER_ROLES
