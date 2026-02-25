"""
Agent Coordinator.

Routes user requests to the appropriate vertical agent.
Phase 1: rule-based routing only (keyword matching).

Usage:
    from modules.backend.agents.coordinator.coordinator import handle, handle_direct, list_agents
    result = await handle("How is the system doing?")
    result = await handle_direct("health_agent", "check health")
    agents = list_agents()
"""

from typing import Any

from modules.backend.core.config import find_project_root, load_yaml_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def _load_agent_registry() -> dict[str, dict]:
    """Load all agent configs from config/agents/*.yaml."""
    agents_dir = find_project_root() / "config" / "agents"
    registry: dict[str, dict] = {}

    if not agents_dir.exists():
        return registry

    import yaml

    for path in sorted(agents_dir.glob("*.yaml")):
        with open(path) as f:
            config = yaml.safe_load(f) or {}
        if config["enabled"]:
            registry[config["agent_name"]] = config

    return registry


def list_agents() -> list[dict[str, Any]]:
    """
    List all available agents with their metadata.

    Returns:
        List of dicts with agent_name, description, keywords, tools
    """
    registry = _load_agent_registry()
    return [
        {
            "agent_name": config["agent_name"],
            "description": config["description"],
            "keywords": config["keywords"],
            "tools": config["tools"],
        }
        for config in registry.values()
    ]


async def handle(user_input: str) -> dict[str, Any]:
    """
    Route a user request to the appropriate agent via keyword matching.

    Args:
        user_input: The user's message

    Returns:
        Dict with agent_name, output text, and metadata

    Raises:
        ValueError: If no agent matches the request
    """
    agent_name = _route(user_input)
    return await _execute(agent_name, user_input)


async def handle_direct(agent_name: str, user_input: str) -> dict[str, Any]:
    """
    Send a message directly to a named agent, bypassing routing.

    Args:
        agent_name: The agent to invoke
        user_input: The user's message

    Returns:
        Dict with agent_name, output text, and metadata

    Raises:
        ValueError: If the agent does not exist
    """
    registry = _load_agent_registry()
    if agent_name not in registry:
        available = ", ".join(registry.keys()) or "none"
        raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

    logger.info("Direct agent invocation", extra={"agent_name": agent_name})
    return await _execute(agent_name, user_input)


async def _execute(agent_name: str, user_input: str) -> dict[str, Any]:
    """Execute a named agent with the given input."""
    if agent_name == "health_agent":
        from modules.backend.agents.vertical.health_agent import run_health_agent

        result = await run_health_agent(user_input)

        return {
            "agent_name": "health_agent",
            "output": result.summary,
            "components": result.components,
            "advice": result.advice,
        }

    raise ValueError(f"Agent '{agent_name}' is registered but has no executor.")


def _route(user_input: str) -> str:
    """
    Rule-based routing. Returns the agent name that should handle this input.

    Phase 1: keyword matching against agent configs.
    Phase 2+: add LLM-based classification fallback.
    """
    text = user_input.lower()
    registry = _load_agent_registry()

    for agent_name, config in registry.items():
        keywords = config["keywords"]
        for keyword in keywords:
            if keyword in text:
                logger.debug(
                    "Routed to agent",
                    extra={"agent_name": agent_name, "keyword": keyword},
                )
                return agent_name

    available = ", ".join(registry.keys()) or "none"
    raise ValueError(f"No agent matched. Available agents: {available}.")
