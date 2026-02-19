# 26 - Agentic AI: PydanticAI Implementation (Optional Module)

*Version: 1.1.0*
*Author: Architecture Team*
*Created: 2026-02-18*

## Changelog

- 1.1.0 (2026-02-18): Added concept-to-implementation mapping table, data model mapping, reconciled SQL schema with AgentTask primitive (field names, feedback column, status CHECK constraint)
- 1.0.0 (2026-02-18): Initial PydanticAI implementation guide

---

## Module Status: Optional

This module is the **implementation companion** to **[25-agentic-architecture.md](25-agentic-architecture.md)**, which defines the conceptual architecture (phases, principles, orchestration patterns, primitive). This document specifies how those concepts are realized using PydanticAI.

**Do not adopt this module without first reading 25-agentic-architecture.md.** The conceptual foundation — the 5 phases, 28 design principles, orchestration Options A-D, tiered delegation, orchestrator evolution — lives there and is not repeated here.

**Dependencies**: 25-agentic-architecture.md, 08-llm-integration.md, 06-event-architecture.md.

---

## Concept-to-Implementation Mapping

This table maps each conceptual component from 25-agentic-architecture.md to its concrete implementation in this document.

| Concept (Doc 25) | Implementation (Doc 26) | Notes |
|-------------------|------------------------|-------|
| **AgentTask primitive** | `agent_runs` table + `agent_messages` table | The single conceptual primitive maps to multiple tables for normalization (see "Data Model Mapping" below) |
| **Orchestrator** | `AgentCoordinator` class in `coordinator/coordinator.py` | Python class, NOT a PydanticAI Agent |
| **Router Agent** (LLM classification) | `LLMRouter` class using a PydanticAI Agent in `coordinator/router_llm.py` | Lightweight single-turn Agent for intent classification |
| **Agent Registry** | `VerticalAgentRegistry` class in `coordinator/registry.py` | Loads from YAML config at startup |
| **Tool Registry** | Tool definitions in agent YAML + `@agent.tool` decorators | PydanticAI handles tool schema generation from function signatures |
| **Execution Engine (ReAct loop)** | PydanticAI's built-in `agent.run()` / `agent.run_stream()` | Framework handles the reasoning loop internally |
| **Horizontal middleware** | `compose()` function in `horizontal/base.py` | Wraps every vertical agent: guardrails → memory → cost → output → agent.run() |
| **Agent-as-tool delegation** | PydanticAI tool function calling child `agent.run(usage=ctx.usage)` | Cost propagation is automatic via `usage` parameter |
| **Budget enforcement** | PydanticAI `UsageLimits` + cost tracking horizontal | `UsageLimits(request_limit, tool_calls_limit, total_tokens_limit)` per run |
| **Kill switch** | API endpoint + task status update to `cancelled` | Coordinator checks status before each step |
| **Approval gates** | `agent_pending_approvals` table + Redis polling | Execution pauses until approval received via API |
| **Reasoning chain** | `reasoning` JSONB field on `agent_runs` | Populated from PydanticAI's message history |
| **Memory (Phase 3)** | pgvector extension + Memory horizontal | Horizontal loads relevant memory before agent.run() |
| **Feedback (Phase 4)** | `feedback` field on `agent_runs` + quality scores on memory entries | Links outcomes to memory for weighted retrieval |

### Data Model Mapping

The AgentTask primitive from 25 is a conceptual single entity. In the database, it maps to multiple tables for practical normalization:

| AgentTask Field | Database Location | Why Separate |
|-----------------|------------------|--------------|
| id, status, agent_type, input, output, reasoning, error, cost, duration, model, timestamps | `agent_runs` table | Core execution record — one row per agent invocation |
| parent_task_id | `agent_runs.parent_run_id` | Self-referential FK for delegation chains |
| plan_id, sequence | `agent_runs.conversation_id` + ordering by `created_at` | Plans are conversations with ordered runs |
| type | `agent_runs.status` + context (root run vs child) | Inferred from position in the hierarchy |
| context (conversation history) | `agent_messages` table | Normalized message-level storage for history replay |
| feedback | `agent_runs.feedback` (JSONB, null until Phase 4) | Added to runs table when Phase 4 is implemented |

The `agent_conversations` table groups related runs into a session. A "plan" in 25's terms is a conversation with multiple agent_runs. The root run is the user's request; child runs are agent work and tool calls.

---

## Technology Decisions

### Primary Agent Runtime: PydanticAI

**Package:** `pydantic-ai` (v1.61.0+, stable post-1.0 API)

PydanticAI is chosen because:
- Built by the Pydantic/FastAPI team — dependency injection (`RunContext[DepsT]`) mirrors FastAPI's `Depends()` pattern
- `output_type` accepts any Pydantic `BaseModel` — the same model validating API responses validates LLM output
- Deterministic testing via `TestModel`, `FunctionModel`, and `ALLOW_MODEL_REQUESTS = False` — no other framework provides this
- Agent-as-tool delegation with automatic cost propagation (`usage=ctx.usage`)
- `instructions` parameter is NOT retained in message history across handoffs — prevents prompt leakage between agents
- MIT license, model-agnostic (20+ providers), minimal abstraction tax
- Tools are plain Python functions with type annotations — no custom DSL

### Selective Use of LangGraph

**Package:** `langgraph` (v1.0.x) — adopt only when a workflow requires:
- Durable checkpointing across process restarts
- `interrupt()`/resume for human approvals spanning hours or days
- Complex branching state machines with cycles

Most agent interactions (80%+) stay in PydanticAI. LangGraph is added for specific workflows, not as the primary runtime. PydanticAI agents integrate as LangGraph nodes when needed.

### Vector Memory: pgvector

**Package:** PostgreSQL `pgvector` extension — used for Phase 3 (Remember) semantic memory.

pgvector is chosen over a separate vector database (Chroma, Pinecone) because:
- Already running on the existing PostgreSQL instance — no new service to deploy
- Same backup, monitoring, and maintenance story
- Sufficient performance for initial memory scale
- Can migrate to a dedicated vector DB later if scale demands

---

## Agent Taxonomy

### Service/Agent Boundary Rule

Logic belongs in `modules/backend/services/` if it operates on domain data without an LLM in the loop. Logic belongs in `modules/agents/` if an LLM decides what to do or what to call.

| Condition | Location |
|-----------|----------|
| Pure data access, transformation, or mutation | `modules/backend/services/` |
| LLM selects which operation to perform | `modules/agents/vertical/` |
| Cross-cutting execution concern (cost, safety, memory) | `modules/agents/horizontal/` |
| Routing and orchestration | `modules/agents/coordinator/` |

### Vertical Agents (Domain Specialists)

A vertical agent is a PydanticAI `Agent` instance scoped to a single domain. It maps to the "Specialist" tier in 25-agentic-architecture.md. Each vertical agent owns:
- Its system prompt (loaded from Markdown file)
- Its tool set (scoped to its domain's services)
- Its output schema (a Pydantic `BaseModel`)
- Its capability declaration (used by the coordinator for routing)

One file per vertical agent. One vertical agent per domain.

### Horizontal Agents (Middleware)

A horizontal agent is an async callable that wraps a vertical agent's execution. It does not select domains. It does not call LLMs directly. It intercepts the execution lifecycle: before the run, after the run, or both.

The composition chain runs in fixed order for every agent execution:

```
guardrails → memory → cost_tracking → output_format → vertical_agent.run()
```

| Horizontal | Before Run | After Run | Failure Behavior |
|-----------|-----------|----------|-----------------|
| Guardrails | Block unsafe/injection input | Validate output safety | Raise exception — abort, no LLM call made |
| Memory | Load short-term (Redis) + long-term (PostgreSQL) context | Save conversation to both stores | Log error, continue with empty history |
| Cost Tracking | — | Record tokens, compute cost, check budgets | Log error, continue — do not abort |
| Output Format | — | Validate and normalize output | Log error, return raw output |

### Agent Coordinator

The coordinator maps to the "Orchestrator" in 25-agentic-architecture.md. It is the single entry point for all agent requests. It is NOT a PydanticAI agent — it is a Python class that:
1. Receives requests from any entry point (FastAPI, Taskiq, Redis Streams, Telegram)
2. Routes to a vertical agent using hybrid routing (rules first, LLM fallback)
3. Wraps the selected vertical agent in the horizontal composition chain
4. Executes and returns the result

---

## Module Structure

```
modules/
├── agents/
│   ├── __init__.py
│   ├── coordinator/
│   │   ├── __init__.py
│   │   ├── coordinator.py          # AgentCoordinator class
│   │   ├── registry.py             # VerticalAgentRegistry
│   │   ├── router_rule.py          # Rule-based routing logic
│   │   ├── router_llm.py           # LLM-based intent classification
│   │   └── models.py               # CoordinatorRequest, CoordinatorResponse
│   ├── vertical/
│   │   ├── __init__.py
│   │   ├── base.py                 # VerticalAgentProtocol, AgentCapability
│   │   └── {agent_name}.py         # One file per vertical agent
│   ├── horizontal/
│   │   ├── __init__.py
│   │   ├── base.py                 # HorizontalAgentProtocol, compose()
│   │   ├── cost_tracking.py
│   │   ├── guardrails.py
│   │   ├── memory.py
│   │   └── output_format.py
│   ├── tools/
│   │   ├── __init__.py
│   │   └── {agent_name}/
│   │       └── {tool_name}.py      # One file per tool group
│   ├── prompts/
│   │   └── {agent_name}/
│   │       ├── system.md           # System prompt (Markdown)
│   │       └── examples.md         # Few-shot examples
│   ├── deps/
│   │   └── {agent_name}.py         # Deps dataclass per agent
│   ├── models.py                   # SQLAlchemy models
│   ├── repository.py               # Data access layer
│   ├── schemas.py                  # Pydantic API schemas
│   └── exceptions.py               # Module-specific exceptions
├── backend/
│   └── ...                         # Unchanged existing structure
config/
└── agents/
    ├── coordinator.yaml
    └── {agent_name}.yaml           # One YAML per vertical agent
tests/
└── agents/
    ├── vertical/
    │   └── test_{agent_name}.py
    ├── horizontal/
    │   └── test_{horizontal_name}.py
    ├── coordinator/
    │   └── test_coordinator.py
    └── integration/
        └── test_{agent_name}_flow.py
```

### File Naming Conventions

| Artifact | Convention | Example |
|----------|-----------|---------|
| Vertical agent | `{agent_name}.py` (snake_case) | `report_agent.py` |
| Horizontal agent | `{concern}.py` | `cost_tracking.py` |
| Tool file | `{tool_group}.py` under `tools/{agent_name}/` | `tools/report_agent/fetch.py` |
| Deps dataclass | `{agent_name}.py` under `deps/` | `deps/report_agent.py` |
| System prompt | `prompts/{agent_name}/system.md` | `prompts/report_agent/system.md` |
| Config | `config/agents/{agent_name}.yaml` | `config/agents/report_agent.yaml` |
| Unit test | `tests/agents/vertical/test_{agent_name}.py` | `test_report_agent.py` |

---

## Vertical Agent Pattern

### Capability Declaration

```python
# modules/agents/vertical/base.py

@dataclass
class AgentCapability:
    agent_name: str
    description: str          # Used by LLM router as routing context
    keywords: list[str]       # Used by rule router for keyword matching
    enabled: bool = True
```

### Dependency Injection

Each vertical agent defines a `@dataclass` for its dependencies. Dependencies are instantiated by the coordinator from the FastAPI DI container and passed at run time.

```python
# modules/agents/deps/report_agent.py

@dataclass
class ReportAgentDeps:
    report_service: ReportService
    user_service: UserService
    user_id: str
    session_id: str
```

### Agent Implementation

```python
# modules/agents/vertical/report_agent.py

from pydantic_ai import Agent, RunContext
from pydantic import BaseModel

_SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "report_agent" / "system.md").read_text()

class ReportOutput(BaseModel):
    summary: str
    report_url: str | None = None
    delegate_to: str | None = None

_agent: Agent[ReportAgentDeps, ReportOutput] = Agent(
    model="",  # Set from YAML config at registration
    deps_type=ReportAgentDeps,
    output_type=ReportOutput,
    instructions=_SYSTEM_PROMPT,
)

@_agent.tool
async def fetch_report_data(ctx: RunContext[ReportAgentDeps], report_id: str) -> dict:
    """Fetch structured data for a given report ID."""
    return await ctx.deps.report_service.get_report_data(report_id)
```

**Tools are thin adapters.** They contain one call to a service method and the type coercion required to match the LLM schema. No business logic in tools.

### Agent-as-Tool Delegation

For tiered delegation (25-agentic-architecture.md, Phase 5), a parent agent calls a child agent inside a tool function. PydanticAI's `usage=ctx.usage` propagates cost tracking automatically:

```python
coordinator = Agent('anthropic:claude-opus-4', instructions='Route to specialists.')
search_worker = Agent('anthropic:claude-haiku-4.5', output_type=SearchResponse)

@coordinator.tool
async def delegate_search(ctx: RunContext[None], query: str) -> str:
    result = await search_worker.run(query, usage=ctx.usage)
    return result.output.model_dump_json()
```

The child agent's cost is automatically included in the parent's usage tracking.

### Dynamic Tool Filtering

PydanticAI's `prepare_tools` enables runtime tool filtering — tools hidden from the LLM based on user role or context:

```python
async def filter_by_role(ctx: RunContext[AgentDeps], tool_defs: list[ToolDefinition]) -> list[ToolDefinition]:
    allowed = TOOL_PERMISSIONS.get(ctx.deps.user_role, set())
    return [td for td in tool_defs if td.name in allowed]

secured_agent = Agent('openai:gpt-4o', deps_type=AgentDeps, prepare_tools=filter_by_role)
```

---

## Coordinator Pattern

### Hybrid Routing

Deterministic rules handle obvious cases cheaply. LLM classification is fallback for ambiguous queries.

```python
# modules/agents/coordinator/coordinator.py

class AgentCoordinator:
    async def handle(self, request: CoordinatorRequest, _depth: int = 0) -> CoordinatorResponse:
        if _depth >= MAX_ROUTING_DEPTH:
            raise RuntimeError(f"Routing depth exceeded {MAX_ROUTING_DEPTH}")

        # Try rule-based routing first (free, instant)
        agent_name = self._rule_router.route(request)

        # Fall back to LLM routing (costs tokens, adds latency)
        if agent_name is None:
            decision = await self._llm_router.route(request.user_input)
            agent_name = decision.agent_name

        # Fall back to default agent if routing fails
        if not self._registry.has(agent_name):
            agent_name = self._fallback

        vertical = self._registry.get(agent_name)
        wrapped = compose(vertical)  # applies horizontal middleware chain
        return await wrapped(request, agent_name)
```

### Loop Prevention

Four complementary layers:
1. **UsageLimits** — PydanticAI built-in: `request_limit`, `tool_calls_limit`, `total_tokens_limit`
2. **Routing depth counter** — `_depth` incremented on each recursive `coordinator.handle()` call
3. **Visited-agent set** — prevents cycles in delegation chains
4. **asyncio timeouts** — hard wall-clock backstop on every operation

### Entry Points

The coordinator exposes a single async method: `handle(request: CoordinatorRequest) -> CoordinatorResponse`. All entry points construct a `CoordinatorRequest` and call it:

| Entry Point | Integration |
|------------|-------------|
| FastAPI | `POST /api/v1/agents/chat` → construct request → `coordinator.handle()` |
| Taskiq | Background task → construct request → `coordinator.handle()` → store result in Redis |
| Redis Streams | Stream consumer → construct request → `coordinator.handle()` |
| Telegram | Bot handler → construct request → `coordinator.handle()` → reply to user |

---

## Horizontal Middleware Pattern

### Composition

```python
# modules/agents/horizontal/base.py

def compose(vertical: VerticalAgentProtocol) -> AgentRunFn:
    """
    Wrap a vertical agent in the full horizontal composition chain.
    Order: guardrails → memory → cost_tracking → output_format → vertical.run
    """
    horizontals = [
        GuardrailsHorizontal(),
        MemoryHorizontal(),
        CostTrackingHorizontal(),
        OutputFormatHorizontal(),
    ]
    # Build nested chain: each horizontal calls next, innermost calls vertical
    ...
```

**Every agent passes through the full chain. No exceptions.** This ensures all agents are observable, cost-tracked, safe, and consistently formatted. Skipping horizontal composition for "simple" agents is an anti-pattern.

### Guardrails Horizontal

Runs BEFORE the LLM call. Blocks prompt injection patterns, enforces input length limits. If blocked, no LLM call is made and no cost is incurred.

### Memory Horizontal

Runs BEFORE (load context) and AFTER (save results). Short-term memory via Redis (session-scoped, TTL-based). Long-term memory via PostgreSQL (persistent, queryable). Phase 3 adds pgvector for semantic retrieval.

### Cost Tracking Horizontal

Runs AFTER the LLM call. Records token usage, computes cost, writes to both structlog and PostgreSQL. Checks budget limits. Does not abort on write failure.

---

## Database Schema

### Core Tables

```sql
CREATE TABLE agent_conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     VARCHAR(255) NOT NULL,
    session_id  UUID NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    updated_at  TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE TABLE agent_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES agent_conversations(id),
    agent_name      VARCHAR(100) NOT NULL,
    role            VARCHAR(20) NOT NULL,
    content         TEXT NOT NULL,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cost_usd        NUMERIC(10,6) DEFAULT 0,
    model_name      VARCHAR(100),
    created_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE TABLE agent_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES agent_conversations(id),
    parent_run_id   UUID REFERENCES agent_runs(id),
    agent_name      VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','awaiting_approval','completed','failed','cancelled')),
    input           JSONB,
    output          JSONB,
    reasoning       JSONB,
    feedback        JSONB,                              -- Phase 4: outcome evaluation (null until then)
    error           TEXT,
    token_input     INTEGER DEFAULT 0,                  -- Maps to AgentTask.token_input
    token_output    INTEGER DEFAULT 0,                  -- Maps to AgentTask.token_output
    cost_usd        NUMERIC(10,6) DEFAULT 0,            -- Maps to AgentTask.cost
    model_name      VARCHAR(100),                       -- Maps to AgentTask.model_used
    prompt_version  VARCHAR(50),                        -- Maps to AgentTask.prompt_version
    duration_ms     INTEGER,                            -- Maps to AgentTask.duration_ms
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE TABLE agent_checkpoints (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES agent_conversations(id),
    agent_name      VARCHAR(100) NOT NULL,
    state           JSONB NOT NULL,
    is_complete     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE TABLE agent_pending_approvals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL,
    agent_name      VARCHAR(100) NOT NULL,
    action          JSONB NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    requested_by    VARCHAR(255) NOT NULL,
    reviewed_by     VARCHAR(255),
    created_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    resolved_at     TIMESTAMP
);
```

The `parent_run_id` self-referential FK on `agent_runs` traces the full delegation chain — coordinator → specialist → worker — enabling cost attribution and debugging per delegation path. This maps to the AgentTask parent/child hierarchy from 25-agentic-architecture.md.

### Redis Key Patterns

| Key Pattern | Type | TTL | Purpose |
|------------|------|-----|---------|
| `agent:session:{session_id}` | JSON string | 3600s | Short-term conversation history |
| `agent:approval:{approval_id}` | JSON string | 86400s | Pending HITL approval state |
| `agent:lock:{conversation_id}` | string | 30s | Distributed lock (prevent concurrent runs) |
| `agent:result:{task_id}` | JSON string | 3600s | Async task result storage |

---

## Configuration

### Agent YAML

```yaml
# config/agents/report_agent.yaml
agent_name: report_agent
description: "Generates, retrieves, and summarises reports"
enabled: true
model: anthropic:claude-sonnet-4-20250514
max_budget_usd: 0.50
keywords:
  - report
  - generate report
  - summarise
  - summary
tools:
  - fetch_report_data
  - get_user_permissions
```

### Coordinator YAML

```yaml
# config/agents/coordinator.yaml
routing:
  strategy: hybrid
  llm_model: anthropic:claude-haiku-4.5
  fallback_agent: fallback_agent
  max_routing_depth: 3

limits:
  max_cost_per_task: 1.00
  max_cost_per_plan: 10.00
  max_cost_per_user_daily: 50.00
  task_timeout_seconds: 300
  plan_timeout_seconds: 1800
```

### Feature Flags

Set `enabled: false` in any agent YAML to disable it without code deployment. The registry skips disabled agents.

---

## Testing

### CI Guardrail

```python
# tests/conftest.py
from pydantic_ai import models
models.ALLOW_MODEL_REQUESTS = False  # Any test that calls a real LLM fails immediately
```

### Unit Testing with TestModel

`TestModel` generates deterministic, schema-valid responses without any LLM. It calls all registered tools to verify they work:

```python
from pydantic_ai.models.test import TestModel

@pytest.mark.asyncio
async def test_report_agent_output_schema(mock_deps):
    with _agent.override(model=TestModel()):
        result = await _agent.run("Summarise all reports", deps=mock_deps)
    assert isinstance(result.output, ReportOutput)
    mock_deps.report_service.get_report_data.assert_awaited()
```

### Scripted Testing with FunctionModel

`FunctionModel` gives full control — write a Python function that returns whatever response your test scenario requires:

```python
from pydantic_ai.models.function import FunctionModel

def mock_routing(messages, info):
    user_msg = messages[0].parts[-1].content.lower()
    if 'billing' in user_msg:
        return ModelResponse(parts=[ToolCallPart('handle_billing', {'query': user_msg})])
    return ModelResponse(parts=[TextPart('How can I help?')])

async def test_coordinator_routes_billing():
    with coordinator.override(model=FunctionModel(mock_routing)):
        result = await coordinator.run('I have a billing question')
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_chat_endpoint(client: AsyncClient):
    with report_agent.override(model=TestModel()):
        response = await client.post(
            "/api/v1/agents/chat",
            json={"message": "Generate a report summary", "session_id": "...", "user_id": "test"},
        )
    assert response.status_code == 200
    assert "output" in response.json()
```

### Agent Testing Pyramid

| Layer | Purpose | Tooling | When |
|-------|---------|---------|------|
| Deterministic | Unit tests with TestModel/FunctionModel | pytest + PydanticAI test models | Every commit (CI) |
| Record/Replay | Captured real LLM sessions replayed deterministically | VCR fixtures | Every commit (CI) |
| Probabilistic | Benchmark suites measuring success rates over multiple runs | pydantic-evals | On-demand |
| Judgment | LLM-as-judge with rubrics and majority voting | Custom evaluation | On-demand |

---

## Observability

### structlog Integration

Bind agent context at the coordinator level using `structlog.contextvars`. All downstream log calls automatically include these fields:

```python
structlog.contextvars.bind_contextvars(
    conversation_id=str(request.conversation_id),
    session_id=str(request.session_id),
    user_id=request.user_id,
    entry_point=request.entry_point.value,
    agent_name=agent_name,
)
```

### What to Log at Each Layer

| Layer | Event Key | Required Fields |
|-------|-----------|-----------------|
| Coordinator | `coordinator.routing` | session_id, entry_point |
| Coordinator | `coordinator.routed` | agent_name, routing_reason, duration_ms |
| Guardrails | `guardrails.violation` | pattern, user_id |
| Cost | `agent.cost` | agent_name, input_tokens, output_tokens, cost_usd |
| Memory | `agent.memory.load` | session_id, history_length |
| Memory | `agent.memory.save` | session_id, conversation_id |
| Vertical agent | `agent.run.start` | agent_name, model |
| Vertical agent | `agent.run.complete` | agent_name, duration_ms |
| Tool | `agent.tool.call` | tool_name, agent_name |
| Tool | `agent.tool.result` | tool_name, duration_ms, success |

Agent logs are written to `data/logs/agents.jsonl` per 12-observability.md.

### OpenTelemetry via Logfire

PydanticAI integrates with Logfire (Pydantic's OTel-based observability). Setting `instrument=True` on agents produces distributed traces spanning HTTP → coordinator → agent → tool → LLM.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/agents/chat` | Synchronous agent interaction |
| `POST` | `/api/v1/agents/chat/async` | Submit for background processing, returns task_id |
| `POST` | `/api/v1/agents/chat/stream` | SSE streaming response |
| `GET` | `/api/v1/agents/results/{task_id}` | Retrieve async task result |
| `GET` | `/api/v1/agents/conversations/{id}` | Conversation history with reasoning |
| `POST` | `/api/v1/agents/approvals/{id}` | Approve/reject pending HITL action |
| `POST` | `/api/v1/agents/cancel` | Kill switch |
| `GET` | `/api/v1/agents/costs` | Cost reporting |
| `GET` | `/api/v1/agents/registry` | List available agents and capabilities |

---

## Anti-Patterns

| Anti-pattern | Why prohibited |
|-------------|---------------|
| Tool calls a repository directly | Bypasses service layer; breaks separation of concerns |
| Agent calls another agent without the coordinator | Bypasses routing, observability, loop prevention, and horizontal composition |
| Vertical agent calls `coordinator.handle()` directly | Creates circular routing; use `delegate_to` in output instead |
| Business logic inside tool functions | Tools are thin adapters; business logic in tools is untestable without agent runtime |
| Model name hardcoded in agent file | Model is configuration; hardcoding prevents swaps without code changes |
| User input interpolated into system prompt | Enables prompt injection; user input is always in the `user` role |
| Skipping horizontal composition for "simple" agents | All agents need cost tracking, guardrails, and observability — no exceptions |
| Storing conversation history in Redis indefinitely | Redis is ephemeral; use TTL and flush to PostgreSQL via Memory horizontal |
| Running LLM-based routing for every request | Rules first, LLM fallback only — avoids unnecessary latency and cost |
| Synchronous blocking calls in async agent tools | Blocks the event loop; use `asyncio.to_thread()` for CPU-bound work |

---

## Adding a New Agent (Walkthrough)

Adding `data_analysis_agent` from zero to working:

1. **Create deps** — `modules/agents/deps/data_analysis_agent.py` — dataclass with injected services
2. **Create prompt** — `modules/agents/prompts/data_analysis_agent/system.md` — Markdown system prompt
3. **Create agent** — `modules/agents/vertical/data_analysis_agent.py` — PydanticAI Agent with tools
4. **Create config** — `config/agents/data_analysis_agent.yaml` — model, keywords, tools, budget
5. **Register** — add to `modules/agents/startup.py` registration loop
6. **Write unit tests** — `tests/agents/vertical/test_data_analysis_agent.py` — TestModel, verify tools called
7. **Write integration test** — `tests/agents/integration/test_data_analysis_agent_flow.py` — full HTTP flow

No coordinator changes needed. The registry auto-discovers the new agent's capabilities. The hybrid router picks it up via keywords (rule) or description (LLM fallback).

---

## Phase-by-Phase Implementation Checklist

### Prerequisites
- [ ] 08-llm-integration.md adopted
- [ ] 06-event-architecture.md adopted
- [ ] PydanticAI installed (`pip install pydantic-ai`)
- [ ] 25-agentic-architecture.md reviewed (conceptual foundation)

### Phase 1: Execute
- [ ] Create `modules/agents/` directory structure
- [ ] Implement `AgentCoordinator` with hybrid routing
- [ ] Implement `VerticalAgentRegistry`
- [ ] Implement horizontal middleware chain (guardrails, cost, output format)
- [ ] Create database migration for agent tables
- [ ] Create at least one vertical agent with tools
- [ ] Create coordinator YAML config with limits
- [ ] Implement FastAPI endpoints (chat, cancel, costs, registry)
- [ ] Implement kill switch (API + CLI)
- [ ] Set up `ALLOW_MODEL_REQUESTS = False` in test conftest
- [ ] Write unit tests with TestModel
- [ ] Write integration tests for routing
- [ ] Add `agents` log source to logging config
- [ ] Configure budget limits

### Phase 2: Plan
- [ ] Implement plan creation in coordinator (multi-step decomposition)
- [ ] Implement step sequencing with dependency tracking
- [ ] Implement shared context between plan steps
- [ ] Implement context summarization (cheap model for compression)
- [ ] Implement confidence signaling in routing decisions
- [ ] Evaluate LangGraph for complex branching workflows
- [ ] Write tests for multi-step plans

### Phase 3: Remember
- [ ] Enable pgvector extension on PostgreSQL
- [ ] Implement Memory horizontal with semantic retrieval
- [ ] Implement memory lifecycle (access counts, archival, summarization)
- [ ] Add memory inspection API endpoints
- [ ] Write tests for memory retrieval accuracy

### Phase 4: Learn
- [ ] Implement feedback collection (human ratings, automated checks)
- [ ] Link feedback to memory entries with quality scores
- [ ] Implement outcome-weighted retrieval
- [ ] Implement performance tracking per agent type
- [ ] Implement performance-based routing in coordinator
- [ ] Write tests for feedback-weighted retrieval

### Phase 5: Autonomy
- [ ] Implement agent proposal mechanism (agent suggests approach before executing)
- [ ] Implement coordinator approval workflow for proposals
- [ ] Implement tiered delegation (agent-as-tool with `usage=ctx.usage`)
- [ ] Implement trust levels per agent based on performance history
- [ ] Implement self-evaluation agent
- [ ] Write tests for proposal and delegation flows

---

## Related Documentation

- [25-agentic-architecture.md](25-agentic-architecture.md) — **Conceptual architecture** (phases, principles, patterns, primitive, orchestrator evolution)
- [08-llm-integration.md](08-llm-integration.md) — LLM provider interface, cost tracking, prompt management
- [06-event-architecture.md](06-event-architecture.md) — Redis Streams for agent events
- [19-background-tasks.md](19-background-tasks.md) — Taskiq for scheduled agent work
- [12-observability.md](12-observability.md) — Logging standards
- [09-authentication.md](09-authentication.md) — RBAC for agent API access
- [04-module-structure.md](04-module-structure.md) — Module boundaries and communication
