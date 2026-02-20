# Building AI agent-first systems: a production reference architecture

**The era of AI agents demands fundamentally different system design.** Traditional API gateways, CRUD endpoints, and static authentication patterns cannot support autonomous agents that discover capabilities, delegate tasks, and make decisions across multi-step workflows. This reference architecture provides concrete, implementable patterns for building agent-first platforms in Python — covering protocols (MCP, A2A), gateway infrastructure, identity, data, observability, and testing. All patterns target production deployment at enterprise scale, with specific attention to regulated financial services environments.

The architecture rests on three emerging open standards now governed by the Linux Foundation's Agentic AI Foundation (AAIF, December 2025): **MCP** (Model Context Protocol) for agent-to-tool communication, **A2A** (Agent-to-Agent Protocol) for inter-agent collaboration, and **agentgateway** for infrastructure control. Together with OAuth 2.1, SPIFFE/SPIRE identity, and OpenTelemetry observability, these form a production-ready stack.

---

## 1. Agent-native API design shifts from CRUD to intent

Traditional CRUD APIs require agents to orchestrate multiple low-level calls — reserving inventory, authorizing payment, scheduling shipping — to accomplish a single business outcome. **Intent APIs** collapse this into a single declarative call expressing the desired outcome, letting the server handle orchestration.

**Intent API pattern:**
```python
# Traditional CRUD: agent must orchestrate 3+ calls
POST /inventory/reserve     {"productId": "SKU-123", "quantity": 1}
POST /payment/authorize     {"customerId": "cust-789", "amount": 42.50}
POST /shipping/schedule     {"orderId": "ORD-456"}

# Intent API: single call expressing business outcome
POST /intents/place-order
{
  "customerId": "cust-789",
  "items": [{"productId": "SKU-123", "quantity": 1}],
  "paymentMethod": "card-on-file"
}
```

For regulated domains like banking, **Planning APIs** extend this further — they propose an execution plan the agent can inspect before committing:

```python
POST /plans/initiate-transfer
{"from": "ACC-001", "to": "ACC-002", "amount": 50000, "currency": "USD"}

# Response: reviewable plan
{
  "planId": "PLAN-3210",
  "steps": [
    {"step": "verify_balance", "status": "sufficient"},
    {"step": "compliance_check", "result": "flagged_for_review"},
    {"step": "execute_transfer", "status": "pending_approval"}
  ],
  "warnings": ["Amount exceeds $10K threshold — requires human approval"],
  "next": {"action": "confirm-plan", "link": "/plans/PLAN-3210/confirm"}
}
```

**Structured error responses** are equally critical. Agents cannot interpret bare HTTP 400 errors. Use RFC 7807 `application/problem+json` extended with recovery hints, valid alternatives, and documentation links:

```json
{
  "type": "https://api.bank.com/errors/invalid-account",
  "title": "Account not found",
  "status": 404,
  "detail": "Account ID 'ACC-999' does not exist in the retail banking domain",
  "suggestions": ["ACC-001", "ACC-002", "ACC-003"],
  "doc_uri": "https://docs.bank.com/errors/404/account-not-found",
  "retry_strategy": {"action": "list_accounts", "endpoint": "/accounts?customer=C-789"}
}
```

The **AgenticAPI framework** provides OpenAPI extensions (`x-action`, `x-category`, `x-preconditions`, `x-intent-impact`) for enriching existing specs with agent-discoverable metadata, while the **Arazzo Specification** (OpenAPI Initiative) defines multi-step workflow semantics across API operations — directly applicable to regulated processes like KYC or loan origination.

Real-world implementations include **Stripe's Agent Toolkit** (`pip install stripe-agent-toolkit`), which provides MCP integration via `https://mcp.stripe.com`, and Stripe's **Agentic Commerce Protocol (ACP)** co-developed with OpenAI, introducing Shared Payment Tokens for agent commerce without exposing raw credentials.

---

## 2. MCP: the protocol connecting agents to tools

The **Model Context Protocol** (MCP), created by Anthropic in 2024 and now under the AAIF, standardizes how LLM-powered agents discover and invoke tools. The Python SDK (`mcp` v1.26.0, MIT license, Python ≥3.10) implements the 2025-11-25 specification revision. A v2.0 is planned for Q1 2026 — pin `mcp>=1.25,<2` for stability.

### Building an MCP server

The high-level **FastMCP** API is recommended for production:

```python
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

mcp = FastMCP("BankingTools", stateless_http=True, json_response=True)

# Tools = actions with side effects (POST/PUT/DELETE equivalents)
@mcp.tool()
async def create_transfer(
    from_account: str, to_account: str, amount: float, currency: str = "USD"
) -> dict:
    """Initiate a fund transfer between accounts.
    Amounts exceeding $10,000 require human approval."""
    if amount > 10000:
        return {"status": "pending_approval", "message": "Requires human review"}
    return {"status": "completed", "transaction_id": "TXN-12345"}

# Resources = read-only data (GET equivalents)
@mcp.resource("account://{account_id}/summary")
def account_summary(account_id: str) -> str:
    """Text summary of account activity for the last 30 days."""
    return f"Account {account_id}: 15 transactions, balance $15,234.56"

# Structured output via Pydantic (spec revision 2025-06-18)
class WeatherData(BaseModel):
    temperature: float = Field(description="Temperature in Celsius")
    condition: str

@mcp.tool()
def get_weather(city: str) -> WeatherData:
    """Returns validated structured data."""
    return WeatherData(temperature=22.5, condition="sunny")

if __name__ == "__main__":
    mcp.run(transport="streamable-http")  # Production: http://localhost:8000/mcp
```

**Streamable HTTP** (introduced March 2025) is the production transport — a single `/mcp` endpoint supporting bidirectional communication, server-initiated notifications via SSE, and compatibility with standard load balancers. Use `stateless_http=True` for horizontal scaling across replicas.

### Mounting on existing FastAPI applications

```python
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

accounts_mcp = FastMCP(name="AccountsServer", stateless_http=True)
payments_mcp = FastMCP(name="PaymentsServer", stateless_http=True)

app = FastAPI()
app.mount("/accounts", accounts_mcp.streamable_http_app())
app.mount("/payments", payments_mcp.streamable_http_app())
```

### MCP authentication follows OAuth 2.1

The MCP authorization spec classifies MCP servers as **OAuth 2.0 Resource Servers**. Key requirements: mandatory PKCE for all clients, RFC 9728 Protected Resource Metadata at `/.well-known/oauth-protected-resource`, RFC 8707 Resource Indicators, and strict token audience validation. MCP servers **must not** pass client tokens through to upstream APIs (preventing confused deputy attacks).

### Wrapping REST APIs as MCP tools

For existing bank APIs, wrap endpoints manually using `httpx.AsyncClient`:

```python
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Bank API Bridge", stateless_http=True, json_response=True)
http = httpx.AsyncClient(base_url="https://api.internal.bank.com/v1",
                         headers={"Authorization": f"Bearer {API_TOKEN}"})

@mcp.tool()
async def get_transaction_history(account_id: str, limit: int = 50) -> dict:
    """Get transaction history for an account."""
    resp = await http.get(f"/accounts/{account_id}/transactions", params={"limit": limit})
    resp.raise_for_status()
    return resp.json()
```

For automated conversion, **FastMCP** (PrefectHQ standalone, ~1M downloads/day) provides `FastMCP.from_openapi()` which generates MCP servers directly from OpenAPI specs, and the `mcp-openapi-proxy` package dynamically generates tools from any OpenAPI v3 specification.

---

## 3. A2A enables inter-agent collaboration

While MCP handles agent-to-tool communication (vertical), the **Agent-to-Agent Protocol** (A2A) handles agent-to-agent collaboration (horizontal). Created by Google in April 2025, now under the Linux Foundation with **150+ partner organizations**, the current stable version is **0.3.0** with a Release Candidate v1.0 specification in progress.

### Agent Cards for discovery

Every A2A agent publishes a JSON metadata document at `/.well-known/agent.json`:

```json
{
  "name": "Compliance Review Agent",
  "version": "2.1.0",
  "url": "https://agents.bank.com/compliance/",
  "capabilities": {"streaming": true, "pushNotifications": true},
  "skills": [{
    "id": "aml_screening",
    "name": "AML Screening",
    "description": "Screen transactions against sanctions lists and PEP databases",
    "tags": ["compliance", "aml", "sanctions"],
    "inputModes": ["application/json"],
    "outputModes": ["application/json"]
  }],
  "securitySchemes": {
    "oauth2": {"type": "oauth2", "flows": {"clientCredentials": {
      "tokenUrl": "https://auth.bank.com/token",
      "scopes": {"compliance:read": "Read compliance data"}
    }}}
  }
}
```

### Task lifecycle drives stateful workflows

A2A tasks progress through **9 states**: `submitted → working → completed` for simple flows, with `input-required` and `auth-required` interrupt states for human-in-the-loop patterns. Terminal states (`completed`, `failed`, `canceled`, `rejected`) are immutable — critical for audit compliance.

### Python implementation with the official SDK

```python
# pip install "a2a-sdk[http-server,postgresql]"
from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import EventQueue
from a2a.server.apps.starlette import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore  # Use PostgreSQL in production
from a2a.types import AgentCard, AgentSkill
from a2a.utils import new_agent_text_message

class ComplianceAgentExecutor(AgentExecutor):
    async def execute(self, context, event_queue: EventQueue):
        result = await self.run_compliance_check(context)
        await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context, event_queue: EventQueue):
        raise Exception("Cancel not supported for compliance checks")

agent_card = AgentCard(
    name="Compliance Agent", version="1.0.0",
    url="http://localhost:9999/",
    capabilities={"streaming": True},
    skills=[AgentSkill(id="aml", name="AML Screening",
                       description="Screen against sanctions",
                       tags=["compliance"])],
)

handler = DefaultRequestHandler(
    agent_executor=ComplianceAgentExecutor(),
    task_store=InMemoryTaskStore()
)
app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
# Run: uvicorn app:app.build() --port 9999
```

**MCP and A2A are complementary**: MCP defines how an agent uses its tools (database queries, API calls); A2A defines how agents collaborate with each other. In enterprise architecture, agents expose A2A interfaces externally while using MCP internally to access tools and data.

---

## 4. Agent gateways replace traditional API gateways

An **agent gateway** is a specialized reverse proxy that understands agentic protocols. Unlike traditional API gateways that handle stateless HTTP request-response, agent gateways manage **stateful JSON-RPC sessions**, **fan-out to multiple MCP servers**, **server-initiated events**, and **per-session tool virtualization**. Token-based rate limiting replaces request-count limits because one LLM request can cost anywhere from $0.001 to $0.50.

### Solo.io agentgateway leads the open-source ecosystem

Written in **Rust** for performance, donated to the Linux Foundation in August 2025 (1.7k GitHub stars, contributors from Microsoft, Apple, AWS, Cisco, Salesforce):

```yaml
# agentgateway configuration: MCP multiplexing
binds:
  - port: 3000
listeners:
  - routes:
    - backends:
      - mcp:
          targets:
            - name: banking-tools
              stdio:
                cmd: python
                args: ["banking_mcp_server.py"]
            - name: compliance-tools
              sse:
                uri: https://compliance.internal/mcp/sse
            - name: legacy-api
              openapi:
                schema:
                  file: openapi.json
                host: api.internal.bank.com
```

Core capabilities include MCP/A2A protocol routing, OpenAPI-to-MCP automatic translation, **Cedar policy engine** for fine-grained RBAC, JWT/mTLS authentication, and built-in OpenTelemetry. The **Agent Mesh** vision combines agentgateway with kgateway and Ambient Mesh for comprehensive zero-trust networking.

For data loss prevention, **Proofpoint Secure Agent Gateway** (Q1 2026 availability) extends enterprise DLP to agent workflows — same policies for human and agent data access, with autonomous classifiers that adapt to data handling patterns.

### Rate limiting must be cost-aware

Traditional request-count limits fail for agents. Implement **token-based rate limiting** using budget units (1 unit = $0.001): a $0.50 request consumes 500 units. Use tiered limits (per-minute, per-hour, per-day) with sliding window algorithms to prevent Denial-of-Wallet attacks.

---

## 5. Agent identity requires cryptographic foundations

Static API keys are insufficient for autonomous agents. The production identity stack has three layers.

### Layer 1: Workload identity via SPIFFE/SPIRE

SPIFFE (CNCF graduated project) provides every agent a cryptographic identity — a short-lived X.509 certificate (typically 1-hour TTL, auto-rotated) tied to its runtime environment:

```bash
# Register an AI agent workload in SPIRE
spire-server entry create \
  -spiffeID spiffe://bank.com/agents/trade-processor \
  -parentID spiffe://bank.com/k8s-node \
  -selector k8s:ns:ai-agents \
  -selector k8s:sa:trade-processor-sa \
  -selector k8s:container-image:registry.bank.com/trade-agent:v2.1
```

No static secrets to manage. Auto-rotation eliminates credential theft risk. Works across Kubernetes, VMs, and multi-cloud.

### Layer 2: Token delegation via Biscuit tokens

**Biscuit tokens** (Eclipse project) use Ed25519 public-key cryptography with a **Datalog-based authorization language**, enabling offline attenuation — an orchestrator can narrow a token's permissions before passing it to a sub-agent without contacting any server:

```python
from biscuit_auth import Biscuit, BiscuitBuilder, PrivateKey, Authorizer
from datetime import datetime, timedelta, timezone

# Orchestrator mints root token
builder = BiscuitBuilder("""
    agent({agent_id});
    right({resource}, "read");
    check if time($time), $time < {expiration};
""", {
    'agent_id': 'trade-processor-001',
    'resource': '/api/v1/accounts',
    'expiration': datetime.now(tz=timezone.utc) + timedelta(hours=1)
})
root_token = builder.build(private_key)

# Attenuate OFFLINE before delegating to sub-agent
attenuated = root_token.append("""
    check if resource($r), operation($op), ["read"].contains($op);
    check if resource($r), $r.starts_with("/api/v1/accounts/checking");
""")
```

Biscuit advantages over macaroons: public-key verification (no shared secrets), built-in revocation IDs, and complex authorization rules via Datalog. Python library: `pip install biscuit-python`.

### Layer 3: OAuth 2.1 Token Exchange for delegation

**RFC 8693 Token Exchange** enables agents to act on behalf of users with full delegation audit trails. The resulting JWT carries an `act` claim identifying the agent:

```json
{
  "sub": "user-12345",
  "aud": "https://api.bank.com/accounts",
  "scope": "read:accounts",
  "act": {
    "sub": "agent:trade-processor-001",
    "iss": "https://auth.bank.com"
  }
}
```

**Microsoft Entra Agent ID** (preview since May 2025) treats agents as first-class identities with conditional access policies, identity protection (anomaly detection), lifecycle governance (mandatory human sponsors), and prompt injection attack detection at the network layer.

Emerging IETF standards to track include **WIMSE** (Workload Identity in Multi-Service Environments), **OAuth On-Behalf-Of for AI Agents** (`draft-oauth-ai-agents-on-behalf-of-user-02`), and **SCIM Extension for Agents** (automated agent lifecycle management).

---

## 6. Data architecture shifts for agent consumption

### Knowledge graphs enable multi-hop reasoning

Vector-only RAG cannot answer questions like "find all accounts linked to PEP entities through beneficial ownership chains." **Graph-RAG** combines knowledge graph traversal with vector similarity search:

```python
from graphiti_core import Graphiti  # Temporal knowledge graphs by Zep

graphiti = Graphiti(uri="bolt://localhost:7687", user="neo4j", password="pw")
await graphiti.add_episode(
    name="kyc_review",
    episode_body="ACME Corp risk upgraded to HIGH due to new beneficial owner...",
    source_description="KYC System",
    reference_time=datetime.now(),
    group_id="compliance_team"
)
results = await graphiti.search("What changed about ACME Corp?", num_results=5)
```

**Semantic layers** (Cube.dev, dbt MetricFlow) act as guardrails ensuring agents use governed, consistent metric definitions. "Revenue" is always calculated the same way regardless of which agent queries it. Gartner elevated semantic layers to **essential infrastructure** in its 2025 Hype Cycle.

### Agent-optimized RAG differs from human-optimized RAG

NVIDIA benchmarks show **page-level chunking** (or 1024-token chunks) works best for agent queries — agents handle larger context windows and benefit from more complete document segments. Agent-optimized RAG uses **agentic plan→route→act→verify loops** where the agent decomposes complex queries into sub-questions, routes each to appropriate retrieval tools, and uses Corrective RAG (CRAG) to verify and re-retrieve if quality is insufficient.

### Event sourcing captures agent decision intent

Every agent action should be an immutable event for regulatory compliance:

```python
from eventsourcing.domain import Aggregate, event

class AgentAction(Aggregate):
    @event("ActionInitiated")
    def __init__(self, agent_id: str, task_id: str, action_type: str):
        self.agent_id = agent_id
        self.tool_calls = []

    @event("ToolCalled")
    def record_tool_call(self, tool_name: str, params: dict, output: dict, cost: float):
        self.tool_calls.append({"tool": tool_name, "params": params, "cost": cost})

    @event("DecisionMade")
    def record_decision(self, reasoning: str, decision: str, confidence: float):
        self.decisions.append({"reasoning": reasoning, "decision": decision})
```

---

## 7. Observability must track behavior, not just infrastructure

Agent observability requires tracking **what agents decide and why** — not just latency and error rates. The **OpenTelemetry GenAI Semantic Conventions** (v1.37+, stable) provide standardized attributes: `gen_ai.agent.id`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.operation.name`.

```python
from opentelemetry import trace
tracer = trace.get_tracer("banking.agents")

async def execute_agent_task(task_id: str, query: str):
    with tracer.start_as_current_span("agent.task") as span:
        span.set_attribute("gen_ai.agent.id", "compliance-agent-01")
        with tracer.start_as_current_span("agent.action.tool_call") as tool_span:
            tool_span.set_attribute("gen_ai.action.tool.name", "kyc_database_lookup")
            result = await kyc_lookup(query)
        with tracer.start_as_current_span("agent.action.llm_query") as llm_span:
            llm_span.set_attribute("gen_ai.request.model", "gpt-4o")
            response = await llm_call(result, query)
            llm_span.set_attribute("gen_ai.usage.output_tokens", response.output_tokens)
```

**Behavioral baselining** adapts UEBA (User and Entity Behavior Analytics) to agents across three dimensions: API/tool usage patterns, data access patterns, and response latency distributions. AI agents move **16x more data** than human users (Obsidian Security, 2025), making anomaly detection essential.

For cost tracking, **LiteLLM** serves as a centralized proxy with per-agent spend attribution, while **Langfuse** (MIT, self-hostable) provides trace-level token and cost tracking across **100+ model price definitions**. The `tokencost` library enables pre-call cost estimation for budget gates.

For banking data sovereignty, **Langfuse** (self-hosted on ClickHouse + Redis + S3) or **Arize Phoenix** (single Docker container) are recommended over SaaS-only options.

---

## 8. Testing agents demands new paradigms

### MCP server testing uses in-memory clients

```python
import pytest
from fastmcp.client import Client
from my_server import mcp

@pytest.fixture
async def client():
    async with Client(transport=mcp) as c:
        yield c

async def test_transfer_tool(client):
    result = await client.call_tool("create_transfer", {
        "from_account": "ACC-001", "to_account": "ACC-002", "amount": 500.00
    })
    assert result.data["status"] == "completed"
```

### Behavioral evaluation uses agentic-specific metrics

**DeepEval** provides six dedicated agentic metrics: TaskCompletionMetric, ToolCorrectnessMetric, ArgumentCorrectnessMetric, PlanQualityMetric, PlanAdherenceMetric, and ToolCallOutputCorrectnessMetric. **Scenario** (by LangWatch) enables multi-turn simulation with configurable judge agents evaluating agent behavior at every turn.

### Red teaming is non-negotiable for financial services

**DeepTeam** (Apache 2.0) covers **50+ vulnerabilities** including 16 agentic-specific ones (DirectControlHijacking, GoalRedirection, MemoryPoisoning) with 20+ attack methods. **PyRIT** (Microsoft) provides 61+ built-in converters for adversarial input transformation. Enkrypt AI's red team assessment of a financial research agent revealed a **75.56% overall risk score** with 95% success rate for encoding attacks — underscoring the need for continuous adversarial testing.

**Inspect AI** (UK AI Security Institute, MIT license) provides sandboxed evaluation environments at three isolation tiers (Docker, Kubernetes, Proxmox) with tamper-proof logs suitable for regulatory compliance. The `kubernetes-sigs/agent-sandbox` CRD adds production runtime isolation with gVisor or Kata Containers.

---

## 9. AGENTS.md and llms.txt make systems agent-discoverable

**AGENTS.md** (introduced August 2025 by OpenAI, now under AAIF) is a Markdown file at the root of a codebase providing AI coding agents with project-specific instructions — build commands, testing procedures, coding conventions, architecture notes. Adopted by **60,000+ projects** and supported by Codex, Cursor, Devin, Gemini CLI, and many more.

```markdown
# BankingPlatform
## Core Commands
• Run tests: `pytest tests/ -v --no-header`
• Lint: `ruff check . && mypy src/`
• Build: `docker compose build`

## Architecture
Python 3.11+, FastAPI, MCP servers in src/mcp/, A2A agents in src/agents/

## Security
• Never hardcode credentials — use environment variables
• All MCP tools must validate inputs via Pydantic
• Transfers > $10K require human-in-the-loop approval
```

**llms.txt** (proposed by Jeremy Howard of fast.ai) provides LLM-consumable site structure at `/llms.txt` in Markdown format, with a companion `/llms-full.txt` containing complete documentation compiled into a single file. Token reduction: **90%+** versus HTML crawling. Supported by Mintlify, Fern, GitBook, Yoast SEO, and VitePress plugins.

---

## 10. Python framework selection for production

### Framework comparison at a glance

| Dimension | **LangGraph 1.0.8** | **CrewAI 0.152** | **AutoGen (AG2) 0.10** |
|-----------|---------------------|------------------|------------------------|
| Architecture | Graph-based (nodes + edges) | Role-based (Crews + Flows) | Conversation-based (message passing) |
| 1.0 GA | **Oct 2025** ✅ | Pre-1.0 | Pre-1.0 |
| Human-in-the-loop | `interrupt()` primitive | Flow-level events | `UserProxyAgent` |
| Monthly downloads | ~6.17M | ~1.38M | Growing |
| Enterprise users | LinkedIn, Replit, Ally Financial | PwC, IBM, NVIDIA | Azure ecosystem |

**LangGraph** is the strongest production choice for banking: 1.0 API stability, checkpointing for audit trails, interrupt-based HITL for compliance approvals, and LangSmith observability. The pattern "prototype with CrewAI, productionize with LangGraph" appears across multiple independent analyses.

### Structured outputs via Instructor

The **Instructor** library (v1.14.5, 3M+ monthly downloads) provides validated structured outputs across any LLM provider:

```python
import instructor
from pydantic import BaseModel, Field

class RiskAssessment(BaseModel):
    risk_score: float = Field(ge=0, le=100, description="Risk score 0-100")
    recommendation: str = Field(description="One of: approve, flag_for_review, block")
    fraud_indicators: list[str]

client = instructor.from_provider("openai/gpt-4o")
assessment = client.chat.completions.create(
    response_model=RiskAssessment,
    messages=[{"role": "user", "content": "Assess: $45K wire to new overseas recipient at 3 AM"}],
    max_retries=3  # Auto-retries with validation feedback
)
```

**PydanticAI** (from the Pydantic team) is emerging as a strong unified option — combining agent framework, structured outputs, MCP integration, and A2A support (`agent.to_a2a()`) in a single package.

---

## Conclusion: a layered architecture for agent-first banking

The production agent-first stack for a multinational bank has seven distinct layers, each with concrete tooling choices:

- **Protocol layer**: MCP v1.26 (agent-to-tool) + A2A v0.3/RC1.0 (agent-to-agent) + Intent/Planning APIs (agent-to-service)
- **Gateway layer**: Solo.io agentgateway (protocol routing, Cedar RBAC, cost-aware rate limiting) + Proofpoint (DLP enforcement)
- **Identity layer**: SPIFFE/SPIRE (workload identity) + Biscuit tokens (delegation) + OAuth 2.1 Token Exchange (user impersonation) + Microsoft Entra Agent ID (lifecycle governance)
- **Data layer**: Neo4j + Graphiti (knowledge graphs) + Cube.dev (semantic layer) + event sourcing (audit trails) + agent-optimized RAG (1024-token chunks, CRAG verification loops)
- **Observability layer**: OpenTelemetry GenAI conventions + Langfuse self-hosted (traces) + LiteLLM (cost tracking) + behavioral baselining (UEBA-adapted)
- **Testing layer**: FastMCP in-memory tests + DeepEval agentic metrics + DeepTeam/PyRIT red teaming + Inspect AI sandboxing
- **Application layer**: LangGraph 1.0 (orchestration) + FastAPI (API surface) + Pydantic v2 (schemas) + Instructor (structured outputs)

The most important architectural insight is that **agents are not just API consumers — they are autonomous identities** requiring the same security rigor as human users. Every agent needs a cryptographic identity, scoped short-lived tokens, behavioral monitoring, and emergency kill switches. The shift from "API-first" to "agent-first" is not incremental — it requires rethinking APIs (intent over CRUD), authentication (delegation over static keys), data (semantic over raw), and testing (behavioral over functional).

Standards are converging rapidly under the Linux Foundation's AAIF. Organizations building on MCP, A2A, and OpenTelemetry GenAI conventions today will be well-positioned as these standards reach 1.0 maturity throughout 2026.