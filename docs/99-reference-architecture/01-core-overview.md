# 01 — Architecture Standards Overview

*Version: 2.4.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 2.4.0 (2026-03-01): Added 16-core-concurrency-and-resilience.md as Core standard. Updated 03, 06, 08, 12, 19, 21, 22 version references.
- 2.3.0 (2026-02-24): Added 27-opt-multi-channel-gateway.md for channel adapters, session management, real-time push, gateway security; updated 01 with P8 Secure by Default
- 2.2.0 (2026-02-24): Added 26-opt-tui-architecture.md for interactive terminal interface (Textual)
- 2.1.0 (2026-02-20): Added 33-ai-agent-first-infrastructure.md for MCP, A2A, agent identity, intent APIs, agent-discoverable endpoints
- 2.0.0 (2026-02-19): Consolidated agentic docs — trimmed 25 to framework-agnostic concepts, rewrote 26 with PydanticAI-native patterns, archived research-25
- 1.9.0 (2026-02-18): Split agentic docs into 25 (conceptual) and 26 (PydanticAI implementation)
- 1.8.0 (2026-02-18): Added 31-ai-agentic-architecture.md for agentic AI systems (agents, orchestration, tools, memory)
- 1.7.0 (2026-02-18): Added 25-opt-telegram-client-integration.md for Telegram Client API (MTProto)
- 1.6.0 (2026-02-18): Renumbered docs; moved deployment to 21-22; added 18-core-deployment-azure.md
- 1.5.0 (2026-02-13): Added 24-opt-telegram-bot-integration.md for Telegram bot integration (aiogram v3)
- 1.4.0 (2025-01-29): Added data/ directory structure for file-based data storage
- 1.3.0 (2025-01-29): Added Python environment management guide (uv vs conda) to 09-core-development-workflow.md
- 1.2.0 (2025-01-29): Added 12-core-testing-standards.md with comprehensive testing guidance
- 1.1.0 (2025-01-27): Added 11-core-project-template.md with complete project structure
- 1.0.0 (2025-01-27): Initial generic architecture standards

---

## Purpose

This document set defines architecture standards for software projects. It is prescriptive, not advisory. These are decisions, not options.

When a technology choice no longer serves the standard, the standard is updated. Individual projects do not deviate; the standard evolves.

---

## Context

Architectural decisions made inconsistently across projects create compounding costs — different teams reinvent the same solutions, onboarding takes longer, and AI code assistants produce inconsistent output without shared conventions. This document set exists to make those decisions once, document them prescriptively, and apply them uniformly.

The structure separates Core standards (which apply to every project unconditionally) from Optional modules (which are adopted per project need). This lets teams skip irrelevant complexity — a backend-only API doesn't need frontend standards — while ensuring that when a capability is adopted, it follows the same patterns everywhere. Optional modules declare their dependencies explicitly, so adopting one module tells you exactly what else you need.

Each document in this set is self-contained enough to be read independently, but they form a coherent whole. Core Principles (02) define the non-negotiable mandates. Backend Architecture (04) and Module Structure (05) define how code is organized. Concurrency and Resilience (16) defines the concurrency model, parallelism patterns, and resilience standards (circuit breakers, retries, timeouts) that apply to all external calls. Coding Standards (07, 23), Testing (12), and Workflow (09) define how code is written and shipped. Security (13), Data Protection (14), and Authentication (06) define how it is secured. Observability (08) defines the three pillars: logs, metrics, and distributed traces. Deployment (17, 18) defines how it runs. Optional modules — Data Layer (20), Events (21), Frontend (22), LLM (30), Telegram (24, 25), Agentic AI (31, 32), Agent-First Infrastructure (33), TUI (26), Multi-Channel Gateway (27) — extend the core when projects need those capabilities.

---

## Structure: Core + Optional Modules

Standards are organized into **Core** (always apply) and **Optional** (adopt as needed) modules.

### Core Standards

These apply to all projects without exception:

| Document | Purpose |
|----------|---------|
| 02-core-principles.md | Non-negotiable architectural mandates |
| 03-core-primitive-identification.md | Identifying the system's fundamental data type |
| 04-core-backend-architecture.md | Backend framework, service layer, API design |
| 05-core-module-structure.md | Module organization and inter-module communication |
| 06-core-authentication.md | Authentication and authorization |
| 13-core-security-standards.md | Application security (OWASP, cryptography, input handling) |
| 14-core-data-protection.md | Data protection and privacy (PII, GDPR, retention) |
| 07-core-python-coding-standards.md | Python file organization, imports, CLI, error handling |
| 08-core-observability.md | Logging, monitoring, debugging, alerting |
| 09-core-development-workflow.md | Git workflow, CI/CD, testing, versioning |
| 10-core-error-codes.md | Error code registry, client handling guide |
| 11-core-project-template.md | Standard project directory structure |
| 12-core-testing-standards.md | Test organization, fixtures, coverage |
| 15-core-background-tasks.md | Background tasks and scheduling (Taskiq) |
| 16-core-concurrency-and-resilience.md | Concurrency model, resilience patterns, Python 3.14 features |
| 17-core-deployment-bare-metal.md | Self-hosted deployment (Ubuntu, systemd, nginx) |
| 18-core-deployment-azure.md | Azure managed services deployment |

### Optional Modules

Adopt these based on project requirements:

| Document | When to Adopt |
|----------|---------------|
| 20-opt-data-layer.md | Projects requiring databases beyond basic PostgreSQL |
| 21-opt-event-architecture.md | Projects with async processing, real-time updates |
| 22-opt-frontend-architecture.md | Projects with web frontends |
| 30-ai-llm-integration.md | Projects using LLM/AI capabilities |
| 23-opt-typescript-coding-standards.md | Projects with TypeScript/React frontends |
| 24-opt-telegram-bot-integration.md | Projects with Telegram bot interfaces |
| 25-opt-telegram-client-integration.md | Projects needing channel scraping, history access (MTProto) |
| 31-ai-agentic-architecture.md | Agentic AI conceptual architecture — framework-agnostic (phases, principles, orchestration patterns, AgentTask primitive) |
| 32-ai-agentic-pydanticai.md | Agentic AI implementation using PydanticAI (coordinator, agents, middleware, testing, database schema). Read 25 first. |
| 33-ai-agent-first-infrastructure.md | Agent-first infrastructure — MCP servers, A2A protocol, agent identity, intent APIs, agent-discoverable endpoints. Independent of 25/26. |
| 26-opt-tui-architecture.md | Terminal User Interface — interactive agent sessions, real-time monitoring, approvals, Textual + Textual Web |
| 27-opt-multi-channel-gateway.md | Multi-channel delivery — channel adapters, session management, real-time WebSocket push, DM pairing, gateway security |

---

## Scope

### In Scope

- Python backend services with thin clients
- Web frontends (React)
- Terminal user interfaces (Textual)
- Command-line interfaces
- Data pipelines and analytics
- General web applications

### Out of Scope

- Mobile-native applications
- Desktop applications (Electron/Tauri)
- Embedded systems
- Gaming applications

### Optional Scope (via modules)

- AI/LLM integration
- Agentic AI systems (autonomous agents, orchestration, tools, memory)
- Agent-first infrastructure (MCP, A2A, agent identity, intent APIs)
- Multi-channel delivery (Telegram, Slack, Discord, WebSocket gateway)
- Real-time data streaming
- Time-series data processing
- Event-driven architectures

---

## Core Philosophy

### Backend-First Architecture

All business logic resides in the backend. Clients are presentation layers only. No business rules, validation logic, or data transformation occurs in clients.

Benefits:
- Single source of truth
- Consistent behavior across all client types
- Security logic centralized
- Easier testing and debugging
- New clients require only API consumption

### Thin Client Mandate

Clients perform three functions only:
1. Present data received from the backend
2. Capture user input and send to backend
3. Handle client-specific UI/UX concerns

Clients never:
- Validate business rules
- Transform data for storage
- Make decisions about application state
- Store business data locally (caching excepted)

### Simplicity Over Cleverness

Prefer boring, proven solutions over novel approaches. Code should be readable by developers unfamiliar with the codebase. Abstractions are introduced only when duplication becomes problematic.

### AI-Assisted Development

Architecture choices favor technologies with extensive AI training data. This maximizes effectiveness of AI coding assistants and reduces development friction.

---

## Adopting Optional Modules

### Decision Criteria

| Module | Adopt When |
|--------|------------|
| 20-opt-data-layer.md | Need time-series, analytics, or advanced caching |
| 21-opt-event-architecture.md | Need async processing, WebSocket, or message queues |
| 22-opt-frontend-architecture.md | Building a web UI |
| 30-ai-llm-integration.md | Integrating AI/LLM capabilities |
| 23-opt-typescript-coding-standards.md | Building React frontend |
| 24-opt-telegram-bot-integration.md | Building Telegram bot interface |
| 25-opt-telegram-client-integration.md | Need channel scraping, message history, or autonomous Telegram access |
| 31-ai-agentic-architecture.md | Agentic AI conceptual architecture — framework-agnostic (phases, principles, patterns) |
| 32-ai-agentic-pydanticai.md | Agentic AI implementation using PydanticAI. Read 25 first. |
| 33-ai-agent-first-infrastructure.md | Exposing platform to external agents (MCP, A2A), agent identity, intent APIs |
| 26-opt-tui-architecture.md | Interactive terminal interface (Textual) for agent sessions, monitoring, approvals |
| 27-opt-multi-channel-gateway.md | Delivering agent interactions through multiple messaging channels (Telegram, Slack, Discord, WebSocket) with cross-channel sessions |

### Module Dependencies

```
        ┌─────────────────────────────────┐
        │  32-ai-agentic-pydanticai.md       │
        │  (optional, implementation)     │
        └──────────────┬──────────────────┘
                       │
                       ▼
        ┌─────────────────────────────────┐
        │  31-ai-agentic-architecture.md     │
        │  (optional, conceptual)         │
        └──────────┬──┬──────────────────┘
                   │  │
        ┌──────────┘  └──────────┐
        │                        │
        ▼                        ▼
┌─────────────────────┐  ┌─────────────────────┐
│ 08-llm-integration  │  │ 06-event-arch.md    │
│    (optional)       │  │    (optional)       │
└─────────────────────┘  └─────────────────────┘

┌─────────────────────────────────┐
│  27-agent-first-infrastructure  │
│  (optional, independent of      │
│   25/26 — composable with them) │
└──────────┬──┬──────────────────┘
           │  │
    ┌──────┘  └──────┐
    │                │
    ▼                ▼
┌────────────┐  ┌────────────┐
│ 03-backend │  │ 09-auth.md │
│  (core)    │  │  (core)    │
└────────────┘  └────────────┘

┌─────────────────────────────────┐
│  27-opt-multi-channel-gateway.md   │
│  (optional — channel delivery, │
│   sessions, WebSocket push)    │
└──────────┬──┬──────────────────┘
           │  │
    ┌──────┘  └──────┐
    │                │
    ▼                ▼
┌────────────┐  ┌──────────────────────┐
│ 03-backend │  │ 20-telegram-bot.md   │
│  (core)    │  │  (optional, first    │
└────────────┘  │   channel adapter)   │
                └──────────────────────┘

┌───────────────┐                       ┌───────────────┐
│ 07-frontend   │                       │ 05-data-layer │
│  (optional)   │                       │  (optional)   │
└───────┬───────┘                       └───────────────┘
        │
        ▼
┌───────────────────────┐
│ 11-typescript-stds.md │
│      (optional)       │
└───────────────────────┘
```

**Cross-cutting core documents** (referenced by most optional modules):

| Core Document | Referenced By |
|---------------|---------------|
| 16-core-concurrency-and-resilience.md | 03, 06, 08, 12, 19, 21, 22, 25, 26 |
| 08-core-observability.md | 03, 06, 08, 19, 21, 22, 24, 25, 26, 29 |

Doc 16 defines the shared resilience patterns (circuit breaker, retry, bulkhead, timeout) and concurrency model (asyncio, thread pools, process pools) that all service-layer and consumer code uses. Doc 08 defines the three-pillar observability standard (logs, metrics, traces) that all components emit into.

If adopting 22-opt-frontend-architecture.md, also adopt 23-opt-typescript-coding-standards.md.
If adopting 32-ai-agentic-pydanticai.md, also adopt 31-ai-agentic-architecture.md, 30-ai-llm-integration.md, and 21-opt-event-architecture.md.
If adopting 33-ai-agent-first-infrastructure.md, ensure 04-core-backend-architecture.md and 06-core-authentication.md are in place (both are core, so always present). Doc 33 is independent of 25/26 but composes naturally with them.
If adopting 27-opt-multi-channel-gateway.md, ensure 04-core-backend-architecture.md and 24-opt-telegram-bot-integration.md are in place. Doc 27 benefits from 25/26 for agent routing but can operate with any backend handler.

---

## When To Update This Standard

Update the standard when:
- A technology becomes unmaintained or deprecated
- Significantly better alternatives emerge with production maturity
- Security vulnerabilities require technology replacement
- Scale requirements exceed current technology capabilities

Do not update for:
- Personal preference
- Novelty or trendiness
- Minor performance improvements
- Single project edge cases

---

## Compliance

All new projects must follow Core standards. Optional modules are adopted per project needs.

Existing projects should migrate toward compliance during major refactoring efforts.

Deviations require documented justification and approval. Approved deviations are tracked for potential standard updates.

---

## Quick Start

For a new project:

1. Apply all Core standards (including 16-core-concurrency-and-resilience.md for resilience patterns)
2. Review Optional modules against project requirements
3. Document which Optional modules are adopted in project README
4. Follow the primitive identification process (03-core-primitive-identification.md)
5. Set up project structure per 04-core-backend-architecture.md
