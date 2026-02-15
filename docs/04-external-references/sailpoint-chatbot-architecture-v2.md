# SailPoint IDN AI Chatbot — Skeleton Extension Guide (v2)

## Porting Assessment: `project_skeleton_bff_python_web` → Azure + SailPoint

*Based on review of the full reference architecture (docs 00-20), codebase, and agent framework research*

*v2.0 — Updated with PydanticAI + LangGraph hybrid architecture, MCP tooling, Langfuse observability*

---

## Changes from v1

| Area | v1 | v2 | Rationale |
|------|----|----|-----------|
| Agent framework | LangGraph-only | PydanticAI primary + LangGraph for HITL workflows | PydanticAI's DI model mirrors FastAPI; LangGraph adds durable checkpointing where needed |
| Tool architecture | Custom `tools.py` | PydanticAI `@agent.tool` with `RunContext[Deps]` + MCP servers | Type-safe DI; MCP for external tool portability |
| Guardrails | Custom `AgentGuardrails` class | PydanticAI `prepare_tools` + deterministic middleware | Dynamic tool filtering per user/role/step |
| Observability | Application Insights only | Langfuse `@observe()` + OTEL + Application Insights | LLM-specific cost/trace visibility per agent |
| Cost control | Basic `cost_tracker.py` | LiteLLM Proxy with per-agent budgets | Production-grade budget enforcement |
| DB connections | Assumed single pool | Dual: SQLAlchemy (app data) + psycopg3 (LangGraph checkpoints) | LangGraph's checkpointer requires psycopg3 |
| Testing | Thin plan | PydanticAI `TestModel` + four-tier test hierarchy | Deterministic agent unit testing |
| Taskiq role | Polling + notifications | Agent execution layer for scheduled/background agents | Leverages existing async infrastructure |
| MCP | Not mentioned | MCP servers for SailPoint and future integrations | Industry standard tool connectivity |

---

## 1. What Carries Over Unchanged

| Component | Location | Status |
|-----------|----------|--------|
| FastAPI app factory (`create_app()`) | `modules/backend/main.py` | ✅ Works as-is |
| Request context middleware | `core/middleware.py` | ✅ Works as-is |
| Exception hierarchy | `core/exceptions.py` | ✅ Extend, don't replace |
| Exception handlers | `core/exception_handlers.py` | ✅ Works as-is |
| Structured logging (structlog) | `core/logging.py` | ✅ Works as-is |
| Pydantic schemas pattern | `schemas/` | ✅ Works as-is |
| API versioning (`/api/v1/`) | `api/v1/` | ✅ Works as-is |
| Health checks | `api/health.py` | ✅ Works as-is |
| Cursor pagination | `core/pagination.py` | ✅ Works as-is |
| Test structure (pytest) | `tests/` | ✅ Works as-is |
| Background tasks (Taskiq) | `tasks/` | ✅ Extend for agent execution |
| React frontend (Vite/Tailwind) | `modules/frontend/` | ✅ Works as-is |

---

## 2. What Needs Modification

### 2.1 BaseService — Add API-Backed Service Base

Your current `BaseService` requires `AsyncSession`. SailPoint services talk to REST APIs, not databases. Add a sibling base class:

```python
# modules/backend/services/base_api.py

import asyncio
import httpx
from modules.backend.core.exceptions import ExternalServiceError
from modules.backend.core.logging import get_logger

class BaseAPIService:
    """Base for services backed by external APIs (SailPoint, etc.)."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client
        self._logger = get_logger(self.__class__.__module__)

    async def _api_call(self, method: str, url: str, **kwargs) -> dict:
        """Execute API call with retry, timeout, and error mapping."""
        try:
            async with asyncio.timeout(30):
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            raise ExternalServiceError(f"API timeout: {method} {url}")
        except httpx.HTTPStatusError as e:
            raise ExternalServiceError(f"API error: {e.response.status_code}")
```

### 2.2 Authentication — Entra ID Instead of Self-Managed JWT

Replace `python-jose` token issuance with MSAL token validation. Keep `python-jose` for JWT decode/verify only.

### 2.3 Configuration — Azure Key Vault for Secrets

Extend `config.py` with Azure and agent settings:

```python
class Settings(BaseSettings):
    # Existing settings...

    # Azure-specific
    azure_keyvault_url: str | None = None
    azure_tenant_id: str = ""
    azure_client_id: str = ""

    # SailPoint
    sailpoint_base_url: str = ""
    sailpoint_client_id: str = ""
    sailpoint_client_secret: str = ""

    # LLM
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-4o"
    llm_provider: str = "azure_openai"  # or "anthropic"

    # Agent (NEW in v2)
    litellm_proxy_url: str = "http://localhost:4000"  # LiteLLM proxy for cost control
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"  # Self-hosted Langfuse
```

### 2.4 Database — Dual Connection Management

**This is a key architectural change from v1.** Your application uses SQLAlchemy (async via asyncpg) for business data. LangGraph's `AsyncPostgresSaver` requires psycopg3 (async) and manages its own connection pool. These are separate connection systems sharing the same PostgreSQL instance.

```python
# modules/backend/core/database.py — extend existing

# EXISTING: SQLAlchemy for app data (conversations, audit, etc.)
engine = create_async_engine(settings.database_url, pool_size=10)

# NEW: psycopg3 pool for LangGraph checkpointing
from psycopg_pool import AsyncConnectionPool

langgraph_pool = AsyncConnectionPool(
    conninfo=settings.database_url.replace("postgresql+asyncpg://", "postgresql://"),
    min_size=2,
    max_size=5,
)
```

Both pools connect to the same database but use different schemas:
- `public` schema: SQLAlchemy models (conversations, audit_log, cost_tracking)
- `langgraph` schema: LangGraph checkpoint tables (auto-created by `AsyncPostgresSaver`)

---

## 3. Architecture: PydanticAI + LangGraph Hybrid

### 3.1 The Core Principle

**PydanticAI is the primary agent runtime.** It handles tool calling, structured outputs, dependency injection, and provider abstraction for all agents.

**LangGraph is used selectively** for workflows that require durable checkpointing, graph-based control flow, and built-in interrupt/resume — specifically the multi-turn access request and access review flows with human-in-the-loop approval gates.

**Anthropic's guidance applies:** start with the simplest pattern that works. Most SailPoint operations (identity search, status check, entitlement lookup) are single-turn tool calls that PydanticAI handles cleanly. Only the approval-gated workflows need LangGraph's state machine.

### 3.2 Agent Dependencies via PydanticAI RunContext

PydanticAI's dependency injection maps directly to your existing service layer. Tools never call repositories or APIs directly — they call services:

```python
# modules/backend/services/agent/deps.py

from dataclasses import dataclass
from modules.backend.services.sailpoint.identity import IdentityService
from modules.backend.services.sailpoint.access_request import AccessRequestService
from modules.backend.services.sailpoint.certification import CertificationService
from modules.backend.services.sailpoint.search import SearchService

@dataclass
class SailPointAgentDeps:
    """Dependencies injected into agent tools via RunContext."""
    identity_service: IdentityService
    access_request_service: AccessRequestService
    certification_service: CertificationService
    search_service: SearchService
    authenticated_user_id: str  # From Entra ID JWT
    user_role: str              # From Entra ID app roles
```

### 3.3 Tool Definitions with Type-Safe DI

```python
# modules/backend/services/agent/tools.py

from pydantic_ai import Agent, RunContext
from .deps import SailPointAgentDeps

identity_agent = Agent(
    'azure_openai:gpt-4o',  # or 'anthropic:claude-sonnet-4-5-20250929'
    deps_type=SailPointAgentDeps,
    system_prompt="You are an identity governance assistant...",
)

@identity_agent.tool
async def search_access_items(
    ctx: RunContext[SailPointAgentDeps],
    query: str,
    item_type: str = "ACCESS_PROFILE",
) -> str:
    """Search for requestable access items matching a description."""
    results = await ctx.deps.search_service.search_requestable_items(
        query=query, item_type=item_type
    )
    return format_search_results(results)

@identity_agent.tool
async def lookup_identity(
    ctx: RunContext[SailPointAgentDeps],
    email: str,
) -> str:
    """Look up a user's identity in SailPoint by email."""
    identity = await ctx.deps.identity_service.find_by_email(email)
    return format_identity(identity)

@identity_agent.tool
async def check_request_status(
    ctx: RunContext[SailPointAgentDeps],
    request_id: str,
) -> str:
    """Check the status of an access request."""
    status = await ctx.deps.access_request_service.get_status(request_id)
    return format_status(status)
```

### 3.4 Dynamic Tool Filtering (Guardrails)

PydanticAI's `prepare_tools` replaces the custom `AgentGuardrails` class from v1. Tools are dynamically filtered per request based on authenticated user role:

```python
# modules/backend/services/agent/tools.py

TOOL_PERMISSIONS = {
    "user": {"search_access_items", "lookup_identity", "check_request_status",
             "submit_access_request"},
    "reviewer": {"search_access_items", "lookup_identity", "check_request_status",
                 "submit_access_request", "get_pending_reviews",
                 "decide_certification_item", "bulk_approve_items"},
    "admin": None,  # None = all tools allowed
}

@identity_agent.tool(prepare=filter_tools_by_role)
async def submit_access_request(
    ctx: RunContext[SailPointAgentDeps],
    access_profile_id: str,
    comment: str,
) -> str:
    """Submit an access request (requires confirmation)."""
    # Deterministic check: user can only request for themselves
    result = await ctx.deps.access_request_service.submit(
        requested_for=ctx.deps.authenticated_user_id,
        item_id=access_profile_id,
        comment=comment,
    )
    return f"Access request {result['id']} submitted. Status: {result['status']}"

def filter_tools_by_role(
    ctx: RunContext[SailPointAgentDeps],
    tool_def: ToolDefinition,
) -> ToolDefinition | None:
    """Filter tools based on user role. Return None to hide tool from agent."""
    allowed = TOOL_PERMISSIONS.get(ctx.deps.user_role)
    if allowed is None:  # admin
        return tool_def
    if tool_def.name in allowed:
        return tool_def
    return None  # Tool hidden from this user
```

### 3.5 LangGraph for HITL Workflows Only

LangGraph is used exclusively for the two workflows that require durable state and human approval gates:

1. **Access request flow** — multi-turn (identify → search → select → confirm → submit → track)
2. **Access review flow** — multi-step (load items → pre-filter → present exceptions → collect decisions → submit → sign-off)

```python
# modules/backend/services/agent/workflows/access_request.py

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import interrupt, Command

class AccessRequestState(TypedDict):
    messages: list
    selected_items: list[dict]
    pending_confirmation: dict | None
    confirmed: bool

async def confirm_submission(state: AccessRequestState):
    """Pause execution and wait for user confirmation."""
    confirmation = interrupt({
        "type": "access_request_confirmation",
        "items": state["selected_items"],
        "message": f"Submit access request for {len(state['selected_items'])} items?"
    })
    return {"confirmed": confirmation == "approve"}

async def execute_submission(state: AccessRequestState):
    """Execute the SailPoint API call after confirmation."""
    if not state["confirmed"]:
        return {"messages": [{"role": "assistant", "content": "Request cancelled."}]}
    # Call SailPoint via service layer
    ...

# Build graph
graph = StateGraph(AccessRequestState)
graph.add_node("confirm", confirm_submission)
graph.add_node("execute", execute_submission)
graph.add_edge(START, "confirm")
graph.add_edge("confirm", "execute")
graph.add_edge("execute", END)

# Compile with PostgreSQL checkpointing
checkpointer = AsyncPostgresSaver(langgraph_pool)
access_request_workflow = graph.compile(checkpointer=checkpointer)
```

### 3.6 Access Review Simplification Flow (Unchanged from v1)

The review workflow design remains valid — it's one of the strongest parts of v1. The implementation changes to use PydanticAI for the tool calling and LangGraph for the state machine:

```
1. User: "I have reviews to do"
2. PydanticAI agent: Calls search_service → GET /v3/certifications (scoped to user)
3. PydanticAI agent: Calls certification_service → GET /v3/certifications/{id}/access-review-items
4. Python service: Pre-processes items through risk scorer (deterministic, not LLM):
   - Low risk + SP AI recommends APPROVE → bulk approve candidate
   - High risk / SoD conflict / unused → exception for human review
5. PydanticAI agent: "You have 47 items. 38 low-risk — approve those? 6 need attention. 3 recommend revoking."
6. User: "Yes, approve the low-risk ones."
7. → Handoff to LangGraph workflow → interrupt() → confirm bulk approve → execute
8. PydanticAI agent: Presents each exception with plain-English summary
9. User: Decides on each (approve/revoke with comment)
10. → LangGraph interrupt() per decision → execute → sign-off when complete
```

The key change from v1: steps 2–5 and 8 use PydanticAI (simple tool calls, no state machine needed). Steps 7 and 9–10 use LangGraph (durable state, interrupt/resume, checkpoint recovery).

---

## 4. Extended Project Structure (v2)

```
project/
├── config/
│   ├── .env.example                    # EXISTING (extend with agent/observability vars)
│   ├── settings/
│   │   ├── app.yaml                    # EXISTING
│   │   ├── llm.yaml                    # NEW - LLM config per doc 08
│   │   └── agents.yaml                 # NEW - agent definitions and limits
│   └── prompts/                        # NEW - per doc 08 guidance
│       ├── system/
│       │   └── identity_assistant.yaml
│       ├── tasks/
│       │   ├── access_request.yaml
│       │   ├── access_review.yaml
│       │   └── item_summarization.yaml
│       └── shared/
│           └── safety_instructions.yaml
│
├── modules/
│   ├── backend/
│   │   ├── main.py                     # EXISTING (add WebSocket route)
│   │   │
│   │   ├── api/
│   │   │   ├── health.py              # EXISTING
│   │   │   ├── v1/
│   │   │   │   ├── endpoints/
│   │   │   │   │   ├── notes.py       # EXISTING (example, remove later)
│   │   │   │   │   ├── chat.py        # NEW - REST chat endpoint
│   │   │   │   │   └── reviews.py     # NEW - review status/history
│   │   │   │   └── __init__.py
│   │   │   └── ws/
│   │   │       └── chat.py            # NEW - WebSocket for streaming
│   │   │
│   │   ├── core/
│   │   │   ├── config.py              # EXISTING (extend)
│   │   │   ├── database.py            # EXISTING (add psycopg3 pool for LangGraph)
│   │   │   ├── dependencies.py        # EXISTING (add agent deps providers)
│   │   │   ├── exceptions.py          # EXISTING (add SailPoint exceptions)
│   │   │   ├── exception_handlers.py  # EXISTING
│   │   │   ├── logging.py            # EXISTING
│   │   │   ├── middleware.py          # EXISTING
│   │   │   ├── pagination.py         # EXISTING
│   │   │   ├── security.py           # EXISTING
│   │   │   ├── utils.py              # EXISTING
│   │   │   ├── auth_entra.py          # NEW - Entra ID auth
│   │   │   └── keyvault.py            # NEW - Azure Key Vault
│   │   │
│   │   ├── models/
│   │   │   ├── base.py               # EXISTING
│   │   │   ├── note.py               # EXISTING (example)
│   │   │   ├── conversation.py        # NEW - conversation history
│   │   │   ├── audit_log.py           # NEW - chatbot action audit trail
│   │   │   └── cost_record.py         # NEW - per-agent LLM cost records
│   │   │
│   │   ├── repositories/
│   │   │   ├── base.py               # EXISTING
│   │   │   ├── note.py               # EXISTING (example)
│   │   │   ├── conversation.py        # NEW
│   │   │   ├── audit.py              # NEW
│   │   │   └── cost.py               # NEW - cost tracking persistence
│   │   │
│   │   ├── schemas/
│   │   │   ├── common.py             # EXISTING
│   │   │   ├── note.py               # EXISTING (example)
│   │   │   ├── chat.py               # NEW
│   │   │   ├── sailpoint.py          # NEW
│   │   │   └── review.py             # NEW
│   │   │
│   │   ├── services/
│   │   │   ├── base.py               # EXISTING (DB-backed)
│   │   │   ├── base_api.py            # NEW - API-backed service base
│   │   │   ├── note.py               # EXISTING (example)
│   │   │   │
│   │   │   ├── sailpoint/             # NEW - SailPoint service layer
│   │   │   │   ├── __init__.py
│   │   │   │   ├── client.py          # OAuth2 token mgmt, httpx client
│   │   │   │   ├── identity.py        # Identity search & resolution
│   │   │   │   ├── access_request.py  # Access request submission
│   │   │   │   ├── certification.py   # Certification/review operations
│   │   │   │   └── search.py          # Entitlement/role/profile search
│   │   │   │
│   │   │   ├── llm/                   # NEW - LLM service (per doc 08)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── provider.py        # Provider abstraction
│   │   │   │   └── prompt_engine.py   # YAML prompt loading + variable injection
│   │   │   │   # NOTE: cost_tracker.py REMOVED — replaced by LiteLLM Proxy
│   │   │   │
│   │   │   └── agent/                 # NEW - Agent layer (REDESIGNED in v2)
│   │   │       ├── __init__.py
│   │   │       ├── deps.py            # SailPointAgentDeps dataclass
│   │   │       ├── tools.py           # PydanticAI tool definitions + filter_tools_by_role
│   │   │       ├── identity_agent.py  # PydanticAI Agent for SailPoint operations
│   │   │       ├── executor.py        # AgentExecutor: unified entry point for all triggers
│   │   │       └── workflows/         # LangGraph workflows (HITL only)
│   │   │           ├── __init__.py
│   │   │           ├── access_request.py  # LangGraph graph for request with confirmation
│   │   │           └── access_review.py   # LangGraph graph for review with bulk/exception flow
│   │   │
│   │   ├── mcp/                       # NEW in v2 - MCP tool servers
│   │   │   ├── __init__.py
│   │   │   └── sailpoint_server.py    # MCP server wrapping SailPoint services
│   │   │
│   │   ├── tasks/                     # EXISTING (EXTENDED in v2)
│   │   │   ├── broker.py             # EXISTING
│   │   │   ├── scheduler.py          # EXISTING
│   │   │   ├── example_tasks.py      # EXISTING (example)
│   │   │   ├── agent_executor.py      # NEW - Taskiq task wrapping agent execution
│   │   │   ├── review_notifications.py # NEW - proactive review reminders
│   │   │   └── request_status_poll.py  # NEW - poll SP for request updates
│   │   │
│   │   └── migrations/               # EXISTING (Alembic)
│   │
│   └── frontend/                      # EXISTING React/Vite/Tailwind
│       └── src/
│           ├── components/
│           │   ├── chat/
│           │   │   ├── ChatWindow.tsx
│           │   │   ├── MessageBubble.tsx
│           │   │   ├── ConfirmationCard.tsx
│           │   │   └── ReviewItemCard.tsx
│           │   └── ...
│           ├── hooks/
│           │   └── useWebSocket.ts
│           └── ...
│
├── tests/
│   ├── unit/
│   │   ├── services/
│   │   │   ├── test_identity_agent.py   # PydanticAI TestModel-based
│   │   │   ├── test_tools.py            # Tool output validation
│   │   │   ├── test_tool_filtering.py   # Role-based tool access
│   │   │   └── test_sailpoint_client.py
│   │   └── ...
│   ├── integration/
│   │   ├── test_sailpoint_api.py        # Against SP sandbox
│   │   ├── test_access_request_flow.py  # LangGraph workflow
│   │   └── test_access_review_flow.py   # LangGraph workflow
│   ├── evaluation/                      # NEW in v2 - LLM output quality
│   │   ├── datasets/                    # Langfuse datasets
│   │   │   ├── access_request_scenarios.json
│   │   │   └── review_summarization.json
│   │   └── run_evals.py
│   └── conftest.py
│
├── infrastructure/                     # NEW - Azure IaC
│   ├── terraform/
│   │   ├── main.tf
│   │   ├── app_service.tf
│   │   ├── keyvault.tf
│   │   ├── postgresql.tf
│   │   ├── redis.tf
│   │   ├── openai.tf
│   │   ├── networking.tf
│   │   └── variables.tf
│   └── azure-pipelines.yml
│
├── requirements.txt                    # EXISTING (extend — see below)
├── pytest.ini                         # EXISTING
├── example.py                         # EXISTING
└── .project_root                      # EXISTING
```

### Key structural changes from v1:

| v1 | v2 | Why |
|----|-----|-----|
| `services/agent/graph.py` | `services/agent/identity_agent.py` | PydanticAI Agent, not LangGraph graph |
| `services/agent/nodes.py` | Removed | PydanticAI doesn't use graph nodes for simple flows |
| `services/agent/state.py` | `services/agent/workflows/*.py` | State only needed in LangGraph workflows |
| `services/agent/tools.py` | Same name, redesigned | PydanticAI `@agent.tool` with `RunContext` DI |
| `services/agent/guardrails.py` | Folded into `tools.py` | `prepare_tools` replaces custom class |
| `services/llm/cost_tracker.py` | Removed | LiteLLM Proxy handles cost tracking |
| — | `mcp/sailpoint_server.py` | MCP server for external tool portability |
| — | `services/agent/executor.py` | Unified agent execution for all trigger types |
| — | `tasks/agent_executor.py` | Taskiq-based background agent execution |
| — | `tests/evaluation/` | LLM output quality evaluation with Langfuse |

---

## 5. Extended requirements.txt (v2)

```txt
# =============================================================================
# Agent Framework (CHANGED in v2)
# =============================================================================
pydantic-ai>=1.0.0              # Primary agent runtime (V1 stable)
langgraph>=1.0.0                # HITL workflows only (1.0 GA)
langgraph-checkpoint-postgres>=0.2.0  # Durable state persistence
psycopg[binary]>=3.1.0          # Required by LangGraph checkpointer (NOT asyncpg)
psycopg-pool>=3.1.0             # Connection pooling for psycopg3

# =============================================================================
# LLM Providers
# =============================================================================
openai>=1.30.0                  # Azure OpenAI SDK
anthropic>=0.30.0               # Anthropic Claude SDK

# =============================================================================
# Observability (NEW in v2)
# =============================================================================
langfuse>=3.0.0                 # LLM-specific tracing and cost tracking
opentelemetry-api>=1.20.0       # OTEL for end-to-end tracing
opentelemetry-sdk>=1.20.0

# =============================================================================
# Cost Control (NEW in v2)
# =============================================================================
litellm>=1.40.0                 # LLM proxy for per-agent budgets (optional, can run as sidecar)

# =============================================================================
# MCP (NEW in v2)
# =============================================================================
mcp>=1.0.0                      # Model Context Protocol server/client

# =============================================================================
# SailPoint
# =============================================================================
sailpoint>=1.4.0                # SailPoint IDN Python SDK

# =============================================================================
# Azure
# =============================================================================
azure-identity>=1.15.0
azure-keyvault-secrets>=4.8.0
msal>=1.28.0

# =============================================================================
# WebSocket
# =============================================================================
websockets>=12.0
```

---

## 6. Observability: Langfuse + Application Insights

### 6.1 LLM-Specific Tracing with Langfuse

Every agent call is traced with `@observe()`, providing per-agent cost attribution, latency tracking, and quality evaluation:

```python
# modules/backend/services/agent/executor.py

from langfuse.decorators import observe, langfuse_context

class AgentExecutor:
    """Unified entry point for all agent executions."""

    @observe(name="sailpoint_agent_run")
    async def run(
        self,
        user_message: str,
        deps: SailPointAgentDeps,
        conversation_id: str,
    ) -> AgentResult:
        # Tag for cost attribution
        langfuse_context.update_current_trace(
            user_id=deps.authenticated_user_id,
            session_id=conversation_id,
            tags=["sailpoint", deps.user_role],
        )

        result = await identity_agent.run(
            user_message,
            deps=deps,
        )

        return AgentResult(
            response=result.data,
            tool_calls=result.all_messages(),
            cost=result.cost(),
        )
```

### 6.2 Four-Tier Testing

| Tier | What | How | When |
|------|------|-----|------|
| Unit | Individual tools produce correct output | PydanticAI `TestModel` — deterministic, no LLM calls | Every PR |
| Integration | Workflows complete correctly | Mock SailPoint API, real LangGraph state machine | Every PR |
| System | End-to-end with real LLM | Staging environment with SP sandbox | Pre-release |
| Evaluation | Output quality, hallucination | Langfuse Datasets with LLM-as-judge scoring | Weekly |

```python
# tests/unit/services/test_identity_agent.py

from pydantic_ai import TestModel

async def test_search_tool_called_for_access_query():
    """Agent correctly calls search_access_items for access requests."""
    with identity_agent.override(model=TestModel()):
        result = await identity_agent.run(
            "I need access to the SAP finance module",
            deps=mock_deps,
        )
        # TestModel returns predictable responses — test tool selection, not LLM output
        assert any(
            call.tool_name == "search_access_items"
            for call in result.all_messages()
            if hasattr(call, "tool_name")
        )
```

---

## 7. Azure Infrastructure Topology (Unchanged from v1)

```
┌─────────────────────────────────────────────────────────┐
│  Azure VNet (10.0.0.0/16)                               │
│                                                         │
│  ┌─────────────────────────┐  ┌──────────────────────┐  │
│  │  App Subnet (10.0.1.0/24) │  │ PE Subnet (10.0.2.0/24)│
│  │                         │  │                      │  │
│  │  Azure App Service      │  │  Private Endpoints:  │  │
│  │  (Python 3.12, P1v3)   │──│  - Azure OpenAI      │  │
│  │                         │  │  - Key Vault         │  │
│  │  Managed Identity ──────│──│  - PostgreSQL        │  │
│  │                         │  │  - Redis             │  │
│  └─────────────────────────┘  └──────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
         │                              │
         │ HTTPS (Entra ID auth)        │ HTTPS (OAuth2)
         │                              │
    ┌────▼─────┐              ┌─────────▼──────────┐
    │  Users   │              │  SailPoint IDN     │
    │  (Web/   │              │  (SaaS)            │
    │  Teams)  │              └────────────────────┘
    └──────────┘
```

---

## 8. Reference Architecture Doc Updates Needed

| Doc | Change Required |
|-----|-----------------|
| 08-llm-integration.md | Add PydanticAI agent patterns, `RunContext` DI, `prepare_tools`, LangGraph for HITL only |
| 09-authentication.md | Add Entra ID authentication flow, MSAL integration |
| 12-observability.md | Add Langfuse integration, OTEL for agent tracing, per-agent cost attribution |
| 14-deployment.md | See 14b-deployment-azure.md (already created) |
| 18-security-standards.md | Add prompt injection mitigation, tool filtering, MCP security considerations |
| 06-event-architecture.md | Add SailPoint event trigger webhook consumption, agent-as-consumer pattern |
| 20-background-tasks.md | Add Taskiq as agent execution layer, `agent_executor.py` pattern |

---

## 9. Implementation Order (Revised)

| Phase | Weeks | What | Key Change from v1 |
|-------|-------|------|--------------------|
| 1 | 1–4 | Azure infra (Terraform), SailPoint API client, **PydanticAI agent** with read-only tools, Langfuse tracing | PydanticAI instead of LangGraph for initial agent |
| 2 | 5–8 | **LangGraph access request workflow** with HITL, Entra ID auth, WebSocket streaming | LangGraph scoped to HITL workflow only |
| 3 | 9–14 | **LangGraph access review workflow**, risk scoring, bulk approve, PydanticAI for item summarization | Clear split: PydanticAI for summarization, LangGraph for state machine |
| 4 | 15–20 | Teams channel, **MCP server for SailPoint**, LiteLLM proxy, prompt injection testing, SOX evidence chain | MCP + LiteLLM are new in v2 |

### Phase 1 Milestone: A working PydanticAI agent that can:
- Search SailPoint for identities and access items via natural language
- Check access request status
- Stream responses via WebSocket
- Trace every call in Langfuse with cost attribution
- Run deterministic unit tests via `TestModel`

This proves the execution pipeline end-to-end before adding complexity.
