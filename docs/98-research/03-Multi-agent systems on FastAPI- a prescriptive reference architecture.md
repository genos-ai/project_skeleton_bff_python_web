# Multi-agent systems on FastAPI: a prescriptive reference architecture

**PydanticAI v1.61.0 and LangGraph v1.0.x together provide the foundation for building production-grade multi-agent systems inside existing Python FastAPI + PostgreSQL + Redis + Taskiq stacks.** PydanticAI delivers type-safe agent definition, structured outputs, and elegant dependency injection that mirrors FastAPI's own DX, while LangGraph adds durable stateful orchestration, checkpointing, and first-class human-in-the-loop support for complex workflows. This report covers every layer of the architecture — from agent runtime APIs and orchestration patterns to database schemas, security controls, observability, and testing — with syntactically valid code and exact package versions.

The key architectural decision is straightforward: **use PydanticAI as the default agent runtime for all agents, and introduce LangGraph only when a workflow requires durable checkpointing, interrupt/resume semantics, or complex branching state machines.** Most request-response agent interactions (80%+ of typical workloads) stay in PydanticAI; LangGraph wraps multi-step approval flows, long-running research pipelines, and orchestrations that must survive process restarts.

---

## PydanticAI agent runtime: API surface and core patterns

**Package**: `pydantic-ai==1.61.0` (released Feb 18, 2026). V1 was released September 4, 2025, with API stability guaranteed until V2 (April 2026 at earliest). Install via `pip install pydantic-ai` or `pip install pydantic-ai-slim[openai,anthropic]` for selective extras. Python ≥3.10 required; status is `Production/Stable`.

The `Agent` class is the central abstraction. Its constructor signature captures the full design philosophy:

```python
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel, Field
from dataclasses import dataclass

@dataclass
class SupportDeps:
    customer_id: int
    db: DatabaseConn

class SupportOutput(BaseModel):
    advice: str = Field(description="Advice returned to the customer")
    block_card: bool = Field(description="Whether to block the card")
    risk: int = Field(description="Risk level", ge=0, le=10)

support_agent = Agent(
    'openai:gpt-4o',
    deps_type=SupportDeps,
    output_type=SupportOutput,
    instructions='You are a support agent in our bank.',
    retries=2,
    instrument=True,
)
```

The `Agent` is generic as `Agent[AgentDepsT, OutputDataT]`. The `instructions` parameter (recommended over the legacy `system_prompt`) is **not retained in message history** across agent handoffs, which prevents prompt leakage between agents. Dynamic instructions use a decorator:

```python
@support_agent.instructions
async def add_context(ctx: RunContext[SupportDeps]) -> str:
    name = await ctx.deps.db.get_name(ctx.deps.customer_id)
    return f"Customer name: {name}"
```

**Tool definition** uses three patterns. The `@agent.tool` decorator provides `RunContext` access for dependency injection. `@agent.tool_plain` omits context. The `Tool` class enables programmatic registration with `prepare` functions for conditional availability:

```python
from pydantic_ai import Tool
from pydantic_ai.tools import ToolDefinition

async def role_gated_prepare(
    ctx: RunContext[SupportDeps], tool_def: ToolDefinition
) -> ToolDefinition | None:
    if ctx.deps.customer_id == 42:
        return tool_def
    return None  # hide tool from this run

@support_agent.tool
async def get_balance(ctx: RunContext[SupportDeps]) -> str:
    return await ctx.deps.db.get_balance(ctx.deps.customer_id)
```

**Run methods** include `agent.run()` (async), `agent.run_sync()`, `agent.run_stream()` (async context manager for streaming), and `agent.iter()` for node-level iteration. All accept `message_history`, `deps`, `model_settings`, `usage_limits`, and `usage` parameters.

**Key deprecations to avoid**: `result_type` → use `output_type`; `result.data` → use `result.output`; `Usage` → use `RunUsage`; `system_prompt` still works but `instructions` is preferred.

---

## Multi-agent coordination: three tiers of complexity

PydanticAI documents three official multi-agent patterns, plus two advanced options. The choice depends on workflow complexity.

**Tier 1 — Agent delegation via tools** is the workhorse pattern. A parent agent calls a child agent inside a tool function, passing `usage=ctx.usage` to propagate cost tracking across the delegation chain:

```python
from pydantic_ai import Agent, RunContext, UsageLimits

coordinator = Agent('openai:gpt-4o', instructions='Route to specialists.')
billing_agent = Agent('openai:gpt-4o-mini', output_type=BillingResponse)
search_agent = Agent('openai:gpt-4o-mini', output_type=SearchResponse)

@coordinator.tool
async def handle_billing(ctx: RunContext[None], query: str) -> str:
    r = await billing_agent.run(query, usage=ctx.usage)
    return r.output.model_dump_json()

@coordinator.tool
async def handle_search(ctx: RunContext[None], query: str) -> str:
    r = await search_agent.run(query, usage=ctx.usage)
    return r.output.model_dump_json()

result = await coordinator.run(
    user_message,
    usage_limits=UsageLimits(request_limit=10, tool_calls_limit=25),
)
```

**Tier 2 — Programmatic handoff** uses application code to orchestrate a sequence of agents, passing `message_history` between them for context continuity:

```python
flight_result = await flight_agent.run(prompt, message_history=history)
seat_result = await seat_agent.run(
    follow_up, message_history=flight_result.all_messages(), usage=usage
)
```

**Tier 3 — LangGraph StateGraph** handles complex branching workflows with durable checkpointing, covered in the next section.

**Advanced patterns** include `pydantic_graph` (dataclass-based state machines within the Pydantic ecosystem) and **output functions** for router patterns where the coordinator's output type is itself a function that triggers the next agent.

---

## Hybrid routing: rules first, LLM fallback

Production coordinators should use **hybrid routing** — deterministic rules handle obvious cases cheaply, with LLM classification as fallback for ambiguous queries. This balances latency, cost, and accuracy:

```python
from pydantic import BaseModel
from enum import Enum

class AgentChoice(str, Enum):
    billing = 'billing'
    search = 'search'
    code = 'code'

class RouteDecision(BaseModel):
    agent: AgentChoice
    confidence: float
    reasoning: str

KEYWORD_ROUTES = {
    'billing': ['invoice', 'payment', 'charge', 'refund'],
    'search': ['find', 'lookup', 'search', 'where'],
    'code': ['debug', 'error', 'compile', 'function'],
}

router_agent = Agent(
    'openai:gpt-4o-mini',  # cheap model for classification
    output_type=RouteDecision,
    instructions='Classify user intent. Return agent choice with confidence.',
)

async def hybrid_route(query: str) -> str:
    q = query.lower()
    for agent_key, keywords in KEYWORD_ROUTES.items():
        if any(kw in q for kw in keywords):
            return agent_key
    decision = await router_agent.run(query)
    if decision.output.confidence < 0.5:
        return 'fallback'
    return decision.output.agent.value
```

---

## Vertical and horizontal agent composition

**Vertical agents** are domain specialists — billing, search, code generation — each with focused tools, prompts, and knowledge. **Horizontal agents** implement cross-cutting concerns — cost tracking, guardrails, PII redaction, output formatting — that wrap every vertical agent uniformly.

The **middleware decorator pattern** composes horizontal concerns around vertical agent calls without modifying the agents themselves:

```python
import functools, time
from dataclasses import dataclass, field

@dataclass
class UsageTracker:
    total_tokens: int = 0
    calls: list[dict] = field(default_factory=list)

def with_cost_tracking(tracker: UsageTracker):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.monotonic()
            result = await func(*args, **kwargs)
            usage = result.usage()
            tracker.total_tokens += usage.input_tokens + usage.output_tokens
            tracker.calls.append({
                'agent': func.__name__,
                'tokens': usage.input_tokens + usage.output_tokens,
                'elapsed': time.monotonic() - start,
            })
            return result
        return wrapper
    return decorator

def with_input_guardrails(func):
    @functools.wraps(func)
    async def wrapper(query: str, *args, **kwargs):
        sanitized = sanitize_input(query)  # raises on injection
        return await func(sanitized, *args, **kwargs)
    return wrapper

tracker = UsageTracker()

@with_input_guardrails
@with_cost_tracking(tracker)
async def run_billing(query: str):
    return await billing_agent.run(query)
```

---

## Loop prevention: four complementary strategies

Multi-agent delegation chains require explicit loop prevention. PydanticAI provides `UsageLimits` as the first line of defense, supplemented by application-level controls:

```python
from dataclasses import dataclass, field
from pydantic_ai import UsageLimits, UsageLimitExceeded

@dataclass
class RoutingContext:
    max_depth: int = 5
    current_depth: int = 0
    visited_agents: set[str] = field(default_factory=set)

    def can_route(self, agent_name: str) -> bool:
        return (self.current_depth < self.max_depth
                and agent_name not in self.visited_agents)

    def enter(self, agent_name: str) -> 'RoutingContext':
        return RoutingContext(
            max_depth=self.max_depth,
            current_depth=self.current_depth + 1,
            visited_agents=self.visited_agents | {agent_name},
        )
```

The four layers are: **UsageLimits** (`request_limit`, `tool_calls_limit`, `total_tokens_limit`) built into every `agent.run()` call; **routing depth counter** tracking delegation depth; **visited-agent set** preventing cycles; and **asyncio timeouts** as a hard backstop (`asyncio.wait_for(agent.run(...), timeout=30.0)`).

---

## Agent capability registry and discovery

Agents declare capabilities through structured metadata, enabling dynamic routing and self-documenting architectures:

```python
@dataclass
class AgentCapability:
    name: str
    description: str
    domains: list[str]
    input_types: list[str]
    confidence_threshold: float = 0.7

class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, tuple[Agent, AgentCapability]] = {}

    def register(self, agent: Agent, capability: AgentCapability):
        self._agents[capability.name] = (agent, capability)

    def discover(self, domain: str) -> list[tuple[Agent, AgentCapability]]:
        return [(a, c) for a, c in self._agents.values() if domain in c.domains]

    def all_capabilities(self) -> list[AgentCapability]:
        return [c for _, c in self._agents.values()]

registry = AgentRegistry()
registry.register(billing_agent, AgentCapability(
    name='billing', description='Invoices, payments, refunds',
    domains=['billing', 'payments', 'subscriptions']
))
```

This pattern aligns with Google's A2A protocol Agent Cards and Microsoft's multi-agent reference architecture, both of which standardize capability declaration for cross-system agent discovery.

---

## LangGraph for complex stateful workflows

**Package**: `langgraph==1.0.x` (GA October 22, 2025). Companion packages: `langgraph-checkpoint-postgres==3.0.4` and `langgraph-checkpoint-redis==0.1.1`. LangGraph 1.0 guarantees backward compatibility until 2.0.

Use LangGraph when a workflow requires **durable checkpointing**, **interrupt/resume for human approval**, **complex branching with cycles**, or **multi-step processes surviving restarts**. The StateGraph API builds typed state machines:

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command

class WorkflowState(TypedDict):
    messages: Annotated[list, add_messages]
    approved: bool
    current_agent: str

def review_node(state: WorkflowState):
    decision = interrupt({
        "question": "Approve this action?",
        "details": state["messages"][-1].content,
    })
    return {"approved": decision == "approve"}

builder = StateGraph(WorkflowState)
builder.add_node("process", process_node)
builder.add_node("review", review_node)
builder.add_node("execute", execute_node)
builder.add_edge(START, "process")
builder.add_edge("process", "review")
builder.add_conditional_edges("review", lambda s: "execute" if s["approved"] else END)
builder.add_edge("execute", END)
```

**PostgreSQL checkpointing** requires `psycopg` with `autocommit=True` and `row_factory=dict_row`:

```python
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

pool = ConnectionPool(
    "postgresql://user:pass@host:5432/langgraph",
    max_size=10,
    kwargs={"autocommit": True, "row_factory": dict_row},
)
checkpointer = PostgresSaver(pool)
checkpointer.setup()  # creates required tables on first run
graph = builder.compile(checkpointer=checkpointer)
```

**Redis checkpointing** uses `langgraph-checkpoint-redis` (maintained by Redis Inc., requires Redis 8.0+):

```python
from langgraph.checkpoint.redis import RedisSaver

with RedisSaver.from_conn_string("redis://localhost:6379") as checkpointer:
    checkpointer.setup()
    graph = builder.compile(checkpointer=checkpointer)
```

**PydanticAI agents integrate as LangGraph nodes** by wrapping `agent.run()` calls inside node functions:

```python
from pydantic_ai import Agent
from langchain_core.messages import AIMessage

pydantic_agent = Agent('openai:gpt-4o', instructions='Research specialist.')

def research_node(state: WorkflowState):
    query = state["messages"][-1].content
    result = pydantic_agent.run_sync(query)
    return {"messages": [AIMessage(content=result.output)]}

builder.add_node("research", research_node)
```

---

## When to reach for LangGraph vs pure PydanticAI

| Criterion | PydanticAI only | Add LangGraph |
|---|---|---|
| Request-response agent tasks | ✅ Default choice | Unnecessary overhead |
| Multi-agent delegation chains | ✅ Tool-based delegation | Only if chains branch/loop |
| Durable checkpointing needed | ❌ No built-in persistence | ✅ First-class PostgreSQL/Redis checkpointers |
| Human-in-the-loop approval | Basic (requires_approval on tools) | ✅ `interrupt()` with full state persistence |
| Long-running workflows (hours/days) | ❌ Not designed for this | ✅ Checkpoint + resume across restarts |
| Complex branching with cycles | Possible via pydantic_graph (Beta) | ✅ Mature StateGraph with conditional edges |
| Type-safe structured outputs | ✅ Superior Pydantic validation | Weaker (TypedDict state) |

---

## PostgreSQL schema for conversation and state management

This schema supports the full lifecycle — conversations, messages with agent attribution, delegation chain tracking, checkpoints, and idempotency:

```sql
CREATE TABLE conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    title       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata    JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_conversations_created ON conversations(created_at DESC);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant','system','tool')),
    content         TEXT,
    agent_id        TEXT,
    tool_calls      JSONB,
    tool_call_id    TEXT,
    token_usage     INTEGER DEFAULT 0,
    model_name      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
) PARTITION BY RANGE (created_at);
CREATE INDEX idx_messages_conv ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_agent ON messages(agent_id);

CREATE TABLE agent_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    parent_run_id    UUID REFERENCES agent_runs(id),
    agent_name       TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','running','completed','failed','cancelled')),
    input            JSONB,
    output           JSONB,
    error            TEXT,
    prompt_tokens    INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens     INTEGER DEFAULT 0,
    model_name       TEXT,
    duration_ms      INTEGER,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_runs_conv ON agent_runs(conversation_id);
CREATE INDEX idx_agent_runs_parent ON agent_runs(parent_run_id)
    WHERE parent_run_id IS NOT NULL;

CREATE TABLE checkpoints (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step_index      INTEGER NOT NULL,
    step_name       TEXT NOT NULL,
    state           JSONB NOT NULL,
    idempotency_key TEXT UNIQUE,
    status          TEXT NOT NULL DEFAULT 'completed',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(run_id, step_index)
);

CREATE TABLE idempotency_keys (
    key        TEXT PRIMARY KEY,
    run_id     UUID NOT NULL REFERENCES agent_runs(id),
    response   JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '24 hours'
);

CREATE TABLE agent_usage (
    id             BIGSERIAL PRIMARY KEY,
    user_id        TEXT NOT NULL,
    session_id     TEXT NOT NULL,
    agent_name     TEXT NOT NULL,
    model          TEXT NOT NULL,
    input_tokens   INT DEFAULT 0,
    output_tokens  INT DEFAULT 0,
    total_tokens   INT DEFAULT 0,
    request_count  INT DEFAULT 0,
    cost_usd       NUMERIC(10,6) DEFAULT 0,
    details        JSONB DEFAULT '{}',
    created_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_usage_user ON agent_usage(user_id, created_at);
CREATE INDEX idx_usage_session ON agent_usage(session_id);
```

The **`parent_run_id`** self-referential foreign key on `agent_runs` traces the full delegation chain — coordinator → specialist → sub-agent — enabling cost attribution and debugging per delegation path.

---

## Redis key patterns for session state

```
# Active session context (ephemeral, hot-path)
session:{session_id}:state           → Hash    TTL: 2h
  Fields: user_id, conversation_id, current_agent, status, last_activity

session:{session_id}:messages        → List    TTL: 2h
  # LPUSH + LTRIM last 50; full history in PostgreSQL

# Agent execution context
agent:{agent_id}:context             → Hash    TTL: 30min
  Fields: run_id, conversation_id, step, model, token_budget_remaining

# Rate limiting
rate_limit:{user_id}:{agent_id}      → String  TTL: 60s
rate_limit:{user_id}:global          → String  TTL: 60s

# Distributed locking
lock:conversation:{conversation_id}  → String  TTL: 30s
lock:tool:{idempotency_key}          → String  TTL: 300s

# Real-time events
channel:agent:{agent_id}:events      → Pub/Sub (no TTL)

# LLM response cache
cache:llm:{prompt_hash}              → String  TTL: 1h
```

PostgreSQL is the **source of truth** for all durable state. Redis handles ephemeral hot-path operations: session context, rate limiting, distributed locks preventing concurrent writes to the same conversation, and pub/sub for real-time agent status updates.

---

## PydanticAI message history serialization

PydanticAI's message history is model-independent and fully serializable, making it the bridge between the agent runtime and your persistence layer:

```python
from pydantic_ai import Agent, ModelMessagesTypeAdapter

agent = Agent('openai:gpt-4o', instructions='Be helpful.')

result1 = await agent.run('What is the capital of France?')

# Serialize for PostgreSQL storage
json_bytes: bytes = result1.all_messages_json()

# Restore from storage
restored = ModelMessagesTypeAdapter.validate_json(json_bytes)

# Continue conversation with history
result2 = await agent.run(
    'And Germany?', message_history=restored
)

# History processors trim context before sending to LLM
async def keep_recent(messages: list) -> list:
    return messages[-10:]

trimmed_agent = Agent('openai:gpt-4o', history_processors=[keep_recent])
```

Messages are composed of `ModelRequest` (containing `UserPromptPart`, `SystemPromptPart`, `ToolReturnPart`) and `ModelResponse` (containing `TextPart`, `ToolCallPart`). All serialize via Pydantic's standard JSON handling.

---

## Security: defense in depth across the agent stack

### Tool access control via `prepare_tools`

PydanticAI's `prepare_tools` parameter enables **dynamic, role-based tool filtering** — tools hidden from the LLM never appear in the function-calling schema:

```python
TOOL_PERMISSIONS: dict[str, set[str]] = {
    "researcher": {"web_search", "read_db"},
    "admin": {"web_search", "read_db", "delete_record"},
}

async def filter_by_role(
    ctx: RunContext[AgentContext], tool_defs: list[ToolDefinition]
) -> list[ToolDefinition]:
    allowed = TOOL_PERMISSIONS.get(ctx.deps.agent_role, set())
    return [td for td in tool_defs if td.name in allowed]

secured_agent = Agent('openai:gpt-4o', deps_type=AgentContext,
                       prepare_tools=filter_by_role)
```

### Prompt injection mitigation

A **four-layer defense** is recommended: input sanitization (regex patterns for known injection vectors), system prompt hardening (explicit behavioral constraints), the dual LLM pattern (unprivileged model processes raw input, privileged model acts on sanitized output), and PydanticAI output validators as the final guardrail:

```python
@safe_agent.output_validator
async def validate_output(ctx: RunContext, result: SafeResponse) -> SafeResponse:
    blocked = ["api_key", "password", "secret", "SSN"]
    for term in blocked:
        if term.lower() in result.answer.lower():
            raise ModelRetry("Response contains sensitive data. Regenerate.")
    return result
```

### Per-agent credential scoping

Each agent receives only the credentials its tools require, via PydanticAI's dependency injection:

```python
@dataclass
class AgentCredentials:
    api_keys: dict[str, str]
    allowed_endpoints: set[str]

CREDENTIAL_VAULT = {
    "researcher": AgentCredentials(
        api_keys={"search": "sk-search-readonly-xxx"},
        allowed_endpoints={"https://api.search.com/v1/query"},
    ),
}

research_agent = Agent('openai:gpt-4o', deps_type=AgentCredentials)

@research_agent.tool
async def search(ctx: RunContext[AgentCredentials], query: str) -> str:
    key = ctx.deps.api_keys.get("search")
    if not key:
        raise PermissionError("No search key for this agent")
    # use scoped key...
```

### Human-in-the-loop approval gates

PydanticAI supports `requires_approval=True` on individual tools. For durable approval workflows, LangGraph's `interrupt()` persists the full graph state while waiting for human input, then resumes exactly where it paused.

---

## Observability: traces, costs, and structured logs

### PydanticAI + Logfire for distributed tracing

**Logfire** (Pydantic's OpenTelemetry-based observability platform) auto-instruments every agent run into a span hierarchy. Setting `instrument=True` on agents or calling `logfire.instrument_pydantic_ai()` globally produces traces spanning HTTP request → coordinator → sub-agent → tool call → LLM request:

```python
import logfire
from pydantic_ai import Agent

logfire.configure()
logfire.instrument_pydantic_ai()
logfire.instrument_fastapi(app)

coordinator = Agent('openai:gpt-4o', instructions='Route tasks', instrument=True)
```

### Cost attribution per agent, user, and session

`result.usage()` returns a `RunUsage` dataclass with `input_tokens`, `output_tokens`, `requests`, and `tool_calls`. Passing `usage=ctx.usage` to child agents **accumulates usage across the delegation chain**:

```python
result = await agent.run(prompt,
    usage_limits=UsageLimits(request_limit=10, total_tokens_limit=50_000))
usage = result.usage()
cost = (usage.input_tokens * 2.50 + usage.output_tokens * 10.00) / 1_000_000
# Persist to agent_usage table
```

### Structured logging with structlog and OTel correlation

```python
import structlog
from opentelemetry import trace

def add_otel_context(logger, method_name, event_dict):
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict

structlog.configure(processors=[
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    add_otel_context,
    structlog.processors.JSONRenderer(),
])
```

**What to log at each layer**: coordinator logs routing decisions, confidence scores, and selected agent. Agents log tool call names, arguments (redacted), and token usage. Tools log external API calls, durations, and error codes. All entries include `session_id` and `trace_id` for correlation.

---

## Testing: from deterministic units to full integration

### TestModel and FunctionModel

PydanticAI provides two test models. **TestModel** generates deterministic data matching JSON schemas without any ML — it calls all registered tools, then returns procedural output. **FunctionModel** gives full control over responses via a Python function:

```python
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai import models, ModelMessage, ModelResponse, TextPart

# Block real API calls globally in tests
models.ALLOW_MODEL_REQUESTS = False

# TestModel — automatic schema-valid responses
async def test_basic():
    with support_agent.override(model=TestModel(custom_output_text='Sunny')):
        result = await support_agent.run('Weather?')
        assert result.output == 'Sunny'

# FunctionModel — deterministic routing test
def mock_coordinator(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    user_msg = messages[0].parts[-1].content.lower()
    if 'billing' in user_msg:
        return ModelResponse(parts=[ToolCallPart('handle_billing', {'query': user_msg})])
    return ModelResponse(parts=[TextPart('How can I help?')])

async def test_routes_billing():
    with coordinator.override(model=FunctionModel(mock_coordinator)):
        result = await coordinator.run('I have a billing question')
```

### Pytest fixtures and FastAPI integration testing

```python
# tests/conftest.py
import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai import models
from fastapi.testclient import TestClient
from app.agents import coordinator, billing_agent
from app.main import app

models.ALLOW_MODEL_REQUESTS = False

@pytest.fixture
def override_all_agents():
    with coordinator.override(model=TestModel()):
        with billing_agent.override(model=TestModel()):
            yield

@pytest.fixture
def client(override_all_agents):
    with TestClient(app) as c:
        yield c

def test_chat_endpoint(client):
    response = client.post("/chat", json={"message": "What's my invoice?"})
    assert response.status_code == 200
```

### The agent testing pyramid

The recommended four-layer testing approach (from Block Engineering, January 2026):

- **Base — Deterministic**: Unit tests with TestModel/FunctionModel. Test tool functions independently. Run in CI on every commit.
- **Reproducible Reality**: Record/replay real LLM sessions (VCR pattern). Commit fixtures. Run in CI.
- **Probabilistic**: Benchmark suites with `pydantic-evals`. Run multiple times, track success rate trends. On-demand, not in CI.
- **Vibes and Judgment**: LLM-as-judge with explicit rubrics and majority voting. On-demand evaluation.

---

## FastAPI integration patterns

PydanticAI ships with built-in adapters for streaming chat interfaces:

```python
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response
from pydantic_ai import Agent
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

agent = Agent('openai:gpt-4o', instructions='Helpful assistant.')
app = FastAPI()

@app.post('/chat')
async def chat(request: Request) -> Response:
    return await VercelAIAdapter.dispatch_request(request, agent=agent)
```

The `AGUIAdapter` and `AGUIApp` provide AG-UI protocol support. For custom streaming, `agent.run_stream()` returns an async context manager with `.stream_text(delta=True)` for SSE integration.

---

## Recommended project directory structure

```
my-agent-project/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── coordinator.py         # Router/coordinator agent
│   │   ├── billing_agent.py       # Vertical specialist
│   │   ├── search_agent.py        # Vertical specialist
│   │   ├── registry.py            # AgentRegistry + capabilities
│   │   └── middleware.py           # Horizontal concerns (decorators)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── billing_tools.py
│   │   ├── search_tools.py
│   │   └── shared_tools.py
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── approval_flow.py       # LangGraph stateful workflows
│   ├── models/
│   │   ├── schemas.py             # Pydantic input/output models
│   │   └── state.py               # State management models
│   ├── api/
│   │   ├── main.py                # FastAPI app
│   │   └── routes/
│   │       ├── chat.py
│   │       └── health.py
│   ├── config/
│   │   ├── settings.py            # Pydantic BaseSettings
│   │   ├── agents.yaml            # Agent metadata configuration
│   │   └── loader.py              # YAML config loader
│   └── infra/
│       ├── database.py            # PostgreSQL connection
│       ├── redis.py               # Redis connection
│       └── observability.py       # Logfire + structlog setup
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_agents.py
│   │   ├── test_tools.py
│   │   └── test_routing.py
│   ├── integration/
│   │   └── test_api.py
│   └── evals/
│       └── datasets/
├── prompts/
│   ├── coordinator.md
│   └── billing.md
├── pyproject.toml
└── .env.example
```

---

## Configuration: YAML + environment hybrid

Agent metadata lives in YAML for easy editing; secrets and infrastructure come from environment variables:

```yaml
# config/agents.yaml
agents:
  coordinator:
    model: "openai:gpt-4o"
    instructions: "Route user queries to the appropriate specialist."
    temperature: 0.3
    max_retries: 2
  billing:
    model: "openai:gpt-4o-mini"
    instructions: "Handle billing, invoices, and payment queries."
    temperature: 0.5
    tools: [get_invoice, process_refund]
  search:
    model: "anthropic:claude-sonnet-4-6"
    instructions: "Perform thorough research on the given topic."
    temperature: 0.7
    tools: [web_search, read_db]
```

```python
# config/loader.py
import yaml
from pydantic import BaseModel

class AgentConfig(BaseModel):
    model: str
    instructions: str
    temperature: float = 0.7
    max_retries: int = 3
    tools: list[str] = []

class AppConfig(BaseModel):
    agents: dict[str, AgentConfig]

def load_config(path: str = "config/agents.yaml") -> AppConfig:
    with open(path) as f:
        return AppConfig(**yaml.safe_load(f))
```

---

## Conclusion: architectural decisions that compound

The most consequential decisions in this architecture are not framework choices but composition boundaries. **PydanticAI's `instructions` (not `system_prompt`) prevents prompt leakage** across agent handoffs — a subtle but critical security property. **`prepare_tools` as the access control surface** means security is enforced at the schema level before the LLM ever sees a tool, not after. **`usage=ctx.usage` propagation** makes cost tracking zero-effort across arbitrarily deep delegation chains.

LangGraph enters the picture sparingly but powerfully. Its `interrupt()` function — combined with PostgreSQL checkpointing — solves the hardest multi-agent problem: pausing a complex workflow mid-execution for human review and resuming hours later with full state fidelity. For the 80% of agent interactions that are request-response, PydanticAI alone delivers better type safety, simpler testing, and lower overhead.

The hybrid routing pattern (rules → LLM fallback) reflects a broader principle: **use deterministic logic wherever possible, reserve LLM inference for genuinely ambiguous decisions.** This applies equally to routing, guardrails, and loop prevention. Every layer where you can avoid an LLM call reduces latency, cost, and unpredictability — the three enemies of production agent systems.