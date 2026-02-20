# Why PydanticAI is the right agent framework for your FastAPI stack

**PydanticAI is the only Python agent framework that treats your existing FastAPI + Pydantic v2 codebase as a first-class citizen rather than an afterthought.** At v1.61.0 with a stable post-1.0 API, MIT license, dependency injection modeled after FastAPI's own patterns, and the only production-grade testing story in the space, it eliminates the integration tax every other framework imposes. The alternatives — CrewAI, LangChain, AutoGen, Swarm — each carry at least one disqualifying deficiency for enterprise greenfield work in early 2026: no testability, vendor lock-in, maintenance-mode status, proprietary licensing, or architectural mismatch with async Python stacks. PydanticAI has real weaknesses (no built-in persistence, immature graph orchestration, smaller ecosystem), but none are architectural dead ends. They're solvable with the tools already in your stack.

---

## PydanticAI earns the slot on technical merit, not hype

PydanticAI reached **v1.0 on September 4, 2025** after 9 months of iteration and 15 million downloads. The team committed to no breaking changes until v2 (earliest April 2026), with 6 months of security patches thereafter. It has since shipped **61 minor releases** in 5 months — aggressive iteration without API breakage. The framework is built by the same team behind Pydantic and FastAPI's validation layer, which means the integration isn't bolted on; it's load-bearing architecture.

The dependency injection system is the clearest differentiator. `RunContext[DepsT]` provides typed, validated access to your application dependencies — database sessions, Redis clients, HTTP clients, auth context — inside every tool function and system prompt generator. Your FastAPI `Depends()` resolves services at the HTTP layer; you pass them into PydanticAI's `deps` at the agent layer. No global state, no closures capturing module-level singletons, no fighting two DI frameworks:

```python
@app.post("/analyze")
async def analyze(db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    deps = AnalysisDeps(db=db, redis=redis, tenant_id=request.state.tenant_id)
    result = await agent.run("Analyze recent transactions", deps=deps)
    return result.output  # Typed Pydantic model, directly serializable by FastAPI
```

The `output_type` parameter accepts any Pydantic `BaseModel`. The same model class that defines your FastAPI response schema validates LLM output — **Field descriptions, constraints (`ge`, `le`, `regex`), and custom validators all apply**. Validation failures trigger automatic retries where the LLM receives the Pydantic error and tries again. Your API contract and your agent contract are the same object.

Tool definitions are plain Python functions with type annotations and docstrings. The framework generates JSON schemas from annotations and extracts parameter descriptions from docstrings. No YAML configuration, no custom DSL, no framework-specific base classes. A tool that queries PostgreSQL looks identical to a tool in your existing codebase — because it is one, with a decorator on top.

---

## The testing story is the real enterprise unlock

This is where PydanticAI creates distance from every competitor. Three mechanisms make deterministic agent testing possible:

**`ALLOW_MODEL_REQUESTS = False`** is a global kill switch. Set it in `conftest.py` and every test that accidentally calls a real LLM raises an exception. This is a CI/CD guardrail that no other framework provides. **`TestModel`** calls every registered tool with schema-valid synthetic data and returns deterministic output — no LLM involved. You can inspect exactly what was sent to the model via `last_model_request_parameters`. **`FunctionModel`** gives you full control: write a Python function that receives the message history and returns whatever response your test scenario requires, including multi-turn tool call sequences.

```python
from pydantic_ai.models.test import TestModel

async def test_transaction_analysis():
    with my_agent.override(model=TestModel(), deps=mock_deps):
        result = await my_agent.run("Check fraud indicators")
        assert isinstance(result.output, FraudReport)
        assert result.output.risk_score >= 0
```

Compare this to the alternatives. **CrewAI has no mock LLM, no test utilities, and no deterministic testing path** — their `crewai test` command runs against a real LLM and produces a scoring table. **LangChain** offers `FakeListChatModel` buried in `langchain_community` with poor documentation and no prompt inspection. **AutoGen** has `ChatCompletionCache` for replay but no purpose-built test doubles. For a CISO building production infrastructure, untestable agent behavior is unacceptable risk.

---

## Every alternative carries a disqualifying deficiency

**OpenAI Swarm is dead.** The GitHub README now redirects to the OpenAI Agents SDK. Swarm had 28 total commits, was synchronous (incompatible with async FastAPI), locked to OpenAI models, had no structured outputs, no testing, and no observability. Its successor, the Agents SDK, remains OpenAI-locked with tracing tied to OpenAI's platform. Neither belongs in a model-agnostic enterprise architecture.

**Microsoft AutoGen entered maintenance mode in October 2025.** Microsoft merged it with Semantic Kernel into the "Microsoft Agent Framework," which is in public preview with GA targeted for Q1 2026. Building on AutoGen now means migrating within 6–12 months to a framework whose API isn't finalized. Adding confusion, the `autogen` package on PyPI is controlled by the AG2 community fork, not Microsoft — Microsoft's actual packages are `autogen-agentchat`, `autogen-core`, and `autogen-ext`. AutoGen 0.4's async architecture was sound, but it has no DI system, no built-in persistence, and benchmark studies describe it as "flexible but fragile at scale."

**CrewAI (v1.9.3, ~44k GitHub stars) has the community momentum but not the engineering foundation.** It has **no dependency injection system** — passing database connections into tools requires closures or global state. Its hierarchical process (manager agent delegating to workers) "frequently misfires in practice" per independent analysis, with tasks executing sequentially regardless. Token overhead is severe: every LLM call includes role/goal/backstory scaffolding, format instructions, and accumulated context. The CLI-centric project structure (`crewai create`, YAML configs) conflicts with embedding into an existing FastAPI application. Most damning for enterprise adoption: practitioners report that "by the time I had the crew working, I would have had it implemented 10 times if I used the LLM API directly."

**LangChain (v1.2.10, ~120k stars) carries three enterprise risks.** First, the abstraction tax: Octomind used LangChain for 12 months and removed it because "our team began spending as much time understanding and debugging LangChain as it did building features." LCEL's pipe-operator DSL adds cognitive overhead that slows team onboarding. Second, **LangGraph's core package uses a proprietary "LangGraph License"** — not MIT — which your legal team must review before adoption. The deployment server uses Elastic-2.0, restricting managed service offerings. Third, a **CVSS 9.3 critical deserialization vulnerability (CVE-2025-68664)** was discovered in `langchain-core` in December 2025, where an LLM prompt could cascade into code execution through serialization pipelines. The dependency tree spans hundreds of transitive packages, each a potential CVE vector. For a CISO, this attack surface is significant.

---

## Where LangGraph genuinely outperforms PydanticAI

Intellectual honesty demands acknowledging that **LangGraph excels at durable, stateful, multi-step workflows** in ways PydanticAI's current architecture does not match. LangGraph's graph-based state machine with PostgreSQL-backed checkpointing (`langgraph-checkpoint-postgres`), time-travel debugging, and built-in human-in-the-loop `interrupt()` primitives is purpose-built for long-running approval workflows and complex branching logic. PydanticAI's `pydantic_graph` module offers similar patterns but **remains in beta** with an unstable API.

The pragmatic answer: use PydanticAI as your primary agent runtime for tool-calling agents, structured extraction, and BFF-layer orchestration. If you encounter a workflow requiring multi-day state persistence with checkpoint recovery, evaluate LangGraph for that specific subsystem — after your legal team clears the license. These frameworks are not mutually exclusive, and PydanticAI's agent-as-tool delegation pattern means a PydanticAI agent can orchestrate calls to a LangGraph workflow without coupling your entire stack.

---

## Semantic Kernel, Haystack, and DSPy solve different problems

**Semantic Kernel (v1.39.4)** is the closest to a legitimate alternative — it has real multi-agent primitives (`GroupChatOrchestration`, `RoundRobinGroupChatManager`) and Microsoft backing. But its **.NET-first DNA causes persistent friction in Python stacks**: the Kernel/Plugin abstraction layer introduces a competing DI container, Python testing ergonomics are poor compared to PydanticAI's `TestModel`, documentation and samples skew heavily toward C#, and the Python SDK still lags behind .NET in feature parity. It would force your team to accommodate a foreign architectural paradigm rather than extending their existing one.

**Haystack (v2.24)** is an excellent RAG and document processing pipeline framework, not a multi-agent orchestrator. It has no inter-agent communication primitives, no role-based coordination, and no multi-agent conversation patterns. Use it as a tool within your PydanticAI agents — powering retrieval — not as the agent framework itself.

**DSPy (v3.1.3)** solves prompt optimization through compile-time tuning with training data. Its global `dspy.configure()` state management isn't thread-safe for multi-tenant FastAPI applications, its ML-research testing paradigm (metrics + evaluation sets) is orthogonal to pytest workflows, and it has no multi-agent coordination whatsoever. Wrong tool entirely.

---

## Honest assessment of PydanticAI's weaknesses

PydanticAI has real gaps that your architecture must compensate for:

- **No built-in conversation persistence.** Message history management is your responsibility. You'll need a PostgreSQL-backed conversation store, which means writing the schema, the async SQLAlchemy models, and the retrieval logic yourself. This is deliberate (the framework avoids opinionated storage), but it's work.
- **No built-in rate limiting.** `UsageLimits` caps token/request counts per run, but production rate limiting against provider APIs requires external implementation via the `AsyncTenacityTransport` wrapper or your own middleware.
- **No built-in caching layer.** LLM response caching must be implemented in your Redis layer — PydanticAI won't do it for you.
- **Graph orchestration is beta.** `pydantic_graph` is explicitly marked unstable. Complex stateful workflows with branching and checkpointing need either custom code or a complementary framework.
- **Smaller ecosystem than LangChain.** At **~14.9k stars** versus LangChain's 120k, there are fewer community examples, tutorials, and third-party integrations. Your team will read source code more often than Stack Overflow answers.
- **Rapid release cadence cuts both ways.** Sixty-one releases in five months means the framework is evolving fast. Pin versions aggressively and test upgrades in CI before promoting.
- **Provider-specific quirks persist.** Gemini cannot use tools simultaneously with native structured output mode. Some OpenAI-compatible providers via OpenRouter/Ollama struggle with function calling. Smaller models frequently fail structured output validation.
- **FastAPI DI and PydanticAI DI are complementary but separate.** There is no automatic bridging — you write the wiring code that passes FastAPI-resolved dependencies into PydanticAI's `deps` parameter.

None of these are architectural dead ends. Persistence, caching, and rate limiting are problems your FastAPI + PostgreSQL + Redis stack already solves. The ecosystem gap is closing rapidly. The beta graph module is optional, not load-bearing.

---

## The framework comparison matrix your architecture review needs

| Dimension | PydanticAI | CrewAI | LangChain/LangGraph | AutoGen | Swarm |
|---|---|---|---|---|---|
| **Version / Status** | v1.61.0, stable | v1.9.3, stable | v1.2.10 / v1.0.7 | Maintenance mode | Dead |
| **License** | MIT | MIT | MIT / **Proprietary (LangGraph)** | MIT | MIT |
| **Dependency injection** | ✅ RunContext\<T\> | ❌ None | ❌ None | ❌ None | ❌ None |
| **Deterministic testing** | ✅ TestModel, FunctionModel, ALLOW_MODEL_REQUESTS | ❌ None | ⚠️ FakeListChatModel (limited) | ⚠️ Cache replay only | ❌ None |
| **Typed structured output** | ✅ Pydantic v2 native | ⚠️ Fragile with non-OpenAI | ✅ Good (post-1.0) | ✅ Supported | ❌ None |
| **Model-agnostic** | ✅ 20+ providers | ✅ Via LiteLLM | ✅ Broad | ✅ Broad | ❌ OpenAI only |
| **FastAPI integration** | ✅ Same-team, native | ⚠️ Manual, blocking | ⚠️ Friction (message types, DI) | ⚠️ Manual | ❌ Sync only |
| **Observability** | ✅ OTel + Logfire | ✅ Third-party integrations | ⚠️ Best with LangSmith (paid) | ✅ OTel built-in | ❌ None |
| **Abstraction tax** | Low (plain Python) | High (role/goal/backstory) | High (LCEL, Runnables) | Medium (3-layer API) | Low (but useless) |
| **Token efficiency** | High (minimal scaffolding) | Low (heavy prompt injection) | Medium | Medium | N/A |
| **Security posture** | Clean (MIT, small deps) | Clean (MIT) | ⚠️ CVE-2025-68664 (CVSS 9.3), large dep tree | Clean | N/A |
| **Long-term viability** | ✅ Pydantic team, funded | ✅ Active but fast-churning | ⚠️ License risk (LangGraph) | ❌ Sunsetting | ❌ Dead |

---

## Conclusion

The decision to adopt PydanticAI is defensible on four pillars that no competitor matches simultaneously. **Integration coherence**: it extends your existing FastAPI + Pydantic v2 architecture rather than competing with it. **Testability**: `TestModel`, `FunctionModel`, and `ALLOW_MODEL_REQUESTS` make deterministic CI/CD possible — a capability absent from CrewAI, AutoGen, and Swarm entirely. **Operational control**: typed dependency injection, OpenTelemetry-native observability, and minimal abstraction overhead mean your team debugs application logic, not framework internals. **Risk profile**: MIT license, small dependency footprint, no critical CVEs, and model-agnostic design eliminate the vendor lock-in and supply-chain concerns that shadow LangGraph's proprietary license and LangChain's attack surface.

The honest trade-off is ecosystem maturity. You're choosing a framework with 14.9k stars over one with 120k. You'll write your own persistence layer, your own rate limiting, your own caching. But for a senior engineering team building greenfield on FastAPI, that's building on your strengths — not outsourcing your architecture to a framework that solves problems you don't have while creating ones you can't afford.