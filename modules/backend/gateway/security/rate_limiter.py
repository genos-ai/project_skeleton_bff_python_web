"""
Gateway Rate Limiter.

Config-driven, per-user, per-channel rate limiting.
Reads limits from config/settings/security.yaml.
Uses in-memory storage; upgrade to Redis for distributed deployments.
"""

import time
from collections import defaultdict

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class RateLimitResult:
    """Result of a rate limit check."""

    def __init__(self, allowed: bool, retry_after_seconds: int = 0) -> None:
        self.allowed = allowed
        self.retry_after_seconds = retry_after_seconds


class GatewayRateLimiter:
    """
    Per-user, per-channel rate limiter.

    Reads limits from security.yaml rate_limiting section.
    Each channel has its own messages_per_minute and messages_per_hour.

    For distributed deployments, replace in-memory dicts with Redis
    INCR + EXPIRE for atomic rate counting.
    """

    def __init__(self) -> None:
        self._minute_requests: dict[str, list[float]] = defaultdict(list)
        self._hour_requests: dict[str, list[float]] = defaultdict(list)

    def check(self, channel: str, user_id: str) -> RateLimitResult:
        """
        Check if a request from this user on this channel is within limits.

        Args:
            channel: Channel name (telegram, slack, etc.)
            user_id: User identifier within the channel

        Returns:
            RateLimitResult indicating whether the request is allowed
        """
        limits = self._get_limits(channel)
        if limits is None:
            return RateLimitResult(allowed=True)

        per_minute = limits.get("messages_per_minute")
        per_hour = limits.get("messages_per_hour")
        now = time.monotonic()
        key = f"{channel}:{user_id}"

        if per_minute is not None:
            result = self._check_window(key, self._minute_requests, now, 60, per_minute)
            if not result.allowed:
                logger.warning(
                    "Rate limit exceeded (per-minute)",
                    extra={"channel": channel, "user_id": user_id, "limit": per_minute},
                )
                return result

        if per_hour is not None:
            result = self._check_window(key, self._hour_requests, now, 3600, per_hour)
            if not result.allowed:
                logger.warning(
                    "Rate limit exceeded (per-hour)",
                    extra={"channel": channel, "user_id": user_id, "limit": per_hour},
                )
                return result

        self._minute_requests[key].append(now)
        self._hour_requests[key].append(now)
        return RateLimitResult(allowed=True)

    def _get_limits(self, channel: str) -> dict | None:
        """Load rate limits for a channel from security.yaml."""
        security_config = get_app_config().security
        rate_limiting = security_config.rate_limiting
        channel_config = getattr(rate_limiting, channel, None)
        return channel_config.model_dump() if channel_config else None

    def _check_window(
        self,
        key: str,
        store: dict[str, list[float]],
        now: float,
        window_seconds: int,
        max_requests: int,
    ) -> RateLimitResult:
        """Check a single rate limit window."""
        cutoff = now - window_seconds
        store[key] = [ts for ts in store[key] if ts > cutoff]

        if len(store[key]) >= max_requests:
            oldest = min(store[key]) if store[key] else now
            retry_after = int(window_seconds - (now - oldest)) + 1
            return RateLimitResult(allowed=False, retry_after_seconds=retry_after)

        return RateLimitResult(allowed=True)


_rate_limiter: GatewayRateLimiter | None = None


def get_rate_limiter() -> GatewayRateLimiter:
    """Get or create the gateway rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GatewayRateLimiter()
    return _rate_limiter
