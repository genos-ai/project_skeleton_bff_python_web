"""
Channel Adapter Interface.

Defines the standard contract for all channel adapters.
Every messaging channel (Telegram, Slack, Discord, WebSocket)
implements ChannelAdapter. The gateway interacts with channels
exclusively through this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from modules.backend.core.utils import utc_now


@dataclass
class ChannelMessage:
    """Standard inbound message format. All channel adapters produce this."""

    channel: str
    user_id: str
    text: str
    session_key: str
    message_id: str | None = None
    group_id: str | None = None
    is_group: bool = False
    reply_to_message_id: str | None = None
    media: list[dict] | None = None
    raw_event: dict | None = None
    received_at: str = field(default_factory=lambda: utc_now().isoformat())


@dataclass
class AgentResponse:
    """Standard outbound response format. Router delivers this through adapters."""

    text: str
    session_key: str
    channel: str
    reply_to_message_id: str | None = None
    media: list[dict] | None = None
    cost_usd: float | None = None
    token_input: int | None = None
    token_output: int | None = None
    duration_ms: int | None = None
    agent_name: str | None = None


class ChannelAdapter(ABC):
    """
    Base class for all channel adapters.

    Each messaging channel implements this interface. The gateway
    interacts with channels exclusively through this contract.
    """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Unique channel identifier (e.g., 'telegram', 'slack', 'discord')."""
        ...

    @abstractmethod
    async def deliver_response(self, response: AgentResponse) -> bool:
        """
        Deliver an agent response through this channel.

        Handles channel-specific formatting (chunking, markdown
        conversion, media attachments). Returns True if delivered.
        """
        ...

    @abstractmethod
    def format_text(self, text: str) -> str:
        """
        Format text for this channel's constraints.

        Handles markdown dialect differences, character limits,
        and other channel-specific formatting requirements.
        """
        ...

    @property
    @abstractmethod
    def max_message_length(self) -> int:
        """Maximum message length for this channel."""
        ...

    async def chunk_message(self, text: str) -> list[str]:
        """
        Split a long message into channel-appropriate chunks.

        Default implementation splits on paragraph boundaries
        within max_message_length.
        """
        if len(text) <= self.max_message_length:
            return [text]

        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= self.max_message_length:
                chunks.append(remaining)
                break

            split_at = remaining[:self.max_message_length].rfind("\n\n")
            if split_at == -1:
                split_at = remaining[:self.max_message_length].rfind("\n")
            if split_at == -1:
                split_at = self.max_message_length

            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip()

        return chunks
