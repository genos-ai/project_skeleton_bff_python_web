# Architecture Standards Overview

*Version: 1.1.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.3.0 (2025-01-29): Added Python environment management guide (uv vs conda) to 13-development-workflow.md
- 1.2.0 (2025-01-29): Added 17-testing-standards.md with comprehensive testing guidance
- 1.1.0 (2025-01-27): Added 16-project-template.md with complete project structure
- 1.0.0 (2025-01-27): Initial generic architecture standards

---

## Purpose

This document set defines architecture standards for software projects. It is prescriptive, not advisory. These are decisions, not options.

When a technology choice no longer serves the standard, the standard is updated. Individual projects do not deviate; the standard evolves.

---

## Structure: Core + Optional Modules

Standards are organized into **Core** (always apply) and **Optional** (adopt as needed) modules.

### Core Standards

These apply to all projects without exception:

| Document | Purpose |
|----------|---------|
| 01-core-principles.md | Non-negotiable architectural mandates |
| 02-primitive-identification.md | Identifying the system's fundamental data type |
| 03-backend-architecture.md | Backend framework, service layer, API design |
| 04-module-structure.md | Module organization and inter-module communication |
| 09-authentication.md | Authentication, authorization, API security |
| 10-python-coding-standards.md | Python file organization, imports, CLI, error handling |
| 12-observability.md | Logging, monitoring, debugging, alerting |
| 13-development-workflow.md | Git workflow, CI/CD, testing, versioning |
| 14-deployment.md | Self-hosted deployment, scaling path |
| 15-error-codes.md | Error code registry, client handling guide |
| 16-project-template.md | Standard project directory structure |
| 17-testing-standards.md | Test organization, fixtures, coverage |

### Optional Modules

Adopt these based on project requirements:

| Document | When to Adopt |
|----------|---------------|
| 05-data-layer.md | Projects requiring databases beyond basic PostgreSQL |
| 06-event-architecture.md | Projects with async processing, real-time updates |
| 07-frontend-architecture.md | Projects with web frontends |
| 08-llm-integration.md | Projects using LLM/AI capabilities |
| 11-typescript-coding-standards.md | Projects with TypeScript/React frontends |

---

## Scope

### In Scope

- Python backend services with thin clients
- Web frontends (React)
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
| 05-data-layer.md | Need time-series, analytics, or advanced caching |
| 06-event-architecture.md | Need async processing, WebSocket, or message queues |
| 07-frontend-architecture.md | Building a web UI |
| 08-llm-integration.md | Integrating AI/LLM capabilities |
| 11-typescript-coding-standards.md | Building React frontend |

### Module Dependencies

```
                    ┌─────────────────────────┐
                    │  08-llm-integration.md  │
                    │       (optional)        │
                    └───────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐    ┌─────────────────────┐    ┌───────────────┐
│ 07-frontend   │    │ 06-event-arch.md    │    │ 05-data-layer │
│  (optional)   │    │    (optional)       │    │  (optional)   │
└───────┬───────┘    └─────────────────────┘    └───────────────┘
        │
        ▼
┌───────────────────────┐
│ 11-typescript-stds.md │
│      (optional)       │
└───────────────────────┘
```

If adopting 07-frontend-architecture.md, also adopt 11-typescript-coding-standards.md.

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

1. Apply all Core standards
2. Review Optional modules against project requirements
3. Document which Optional modules are adopted in project README
4. Follow the primitive identification process (02-primitive-identification.md)
5. Set up project structure per 03-backend-architecture.md
