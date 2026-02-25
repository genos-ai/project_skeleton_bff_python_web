"""
Agent Endpoints.

REST API for agent interaction: chat, direct invocation, and registry listing.
"""

from typing import Any

from pydantic import BaseModel, Field

from fastapi import APIRouter

from modules.backend.core.dependencies import RequestId
from modules.backend.core.logging import get_logger
from modules.backend.schemas.base import ApiResponse

logger = get_logger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Request body for agent chat."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User message to send to the agent",
    )
    agent: str | None = Field(
        default=None,
        description="Target a specific agent by name, bypassing routing.",
    )


class ChatResponse(BaseModel):
    """Response from an agent."""

    agent_name: str
    output: str
    components: dict[str, str] | None = None
    advice: str | None = None


class AgentInfo(BaseModel):
    """Agent registry entry."""

    agent_name: str
    description: str
    keywords: list[str]
    tools: list[str]


@router.post(
    "/chat",
    response_model=ApiResponse[ChatResponse],
    summary="Chat with an agent",
    description="Send a message to the agent coordinator. Optionally target a specific agent with the 'agent' field.",
)
async def agent_chat(
    data: ChatRequest,
    request_id: RequestId,
) -> ApiResponse[ChatResponse]:
    """Send a message to an agent (routed or direct)."""
    if data.agent:
        from modules.backend.agents.coordinator.coordinator import handle_direct
        result = await handle_direct(data.agent, data.message)
    else:
        from modules.backend.agents.coordinator.coordinator import handle
        result = await handle(data.message)

    return ApiResponse(
        data=ChatResponse(
            agent_name=result["agent_name"],
            output=result["output"],
            components=result.get("components"),
            advice=result.get("advice"),
        ),
    )


@router.get(
    "/registry",
    response_model=ApiResponse[list[AgentInfo]],
    summary="List available agents",
    description="Returns all enabled agents with their capabilities and keywords.",
)
async def agent_registry(
    request_id: RequestId,
) -> ApiResponse[list[AgentInfo]]:
    """List all available agents."""
    from modules.backend.agents.coordinator.coordinator import list_agents

    agents = list_agents()
    return ApiResponse(
        data=[AgentInfo(**a) for a in agents],
    )
