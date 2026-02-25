"""Channel Adapter Interface — re-exports from base."""

from modules.backend.gateway.adapters.base import (
    AgentResponse,
    ChannelAdapter,
    ChannelMessage,
)

__all__ = [
    "AgentResponse",
    "ChannelAdapter",
    "ChannelMessage",
]
