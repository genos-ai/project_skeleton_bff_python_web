# Architecture

## Overview

This project follows a Backend-for-Frontend (BFF) pattern with a Python backend and React frontend.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                         │
│                     modules/frontend/                            │
└─────────────────────────────────────────────────────────────────┘
                               │
                               │ HTTP/REST
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BFF Layer (FastAPI)                         │
│                     modules/backend/                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  API Layer  │──│  Services   │──│     Repositories        │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
┌─────────────────────────┐       ┌─────────────────────────┐
│      PostgreSQL         │       │         Redis           │
│    (Primary Store)      │       │   (Cache/Tasks/Queue)   │
└─────────────────────────┘       └─────────────────────────┘
```

## Backend Layers

| Layer | Responsibility | Location |
|-------|----------------|----------|
| API | HTTP handlers, request/response | `modules/backend/api/` |
| Services | Business logic, orchestration | `modules/backend/services/` |
| Repositories | Data access, queries | `modules/backend/repositories/` |
| Models | Database entities | `modules/backend/models/` |
| Schemas | Pydantic models | `modules/backend/schemas/` |

## Key Principles

1. **Backend owns all business logic** - Frontend is presentation only
2. **Layered architecture** - Each layer only calls the layer below
3. **Absolute imports** - No relative imports
4. **No hardcoded values** - All config from YAML/env files
5. **Fail fast** - Missing config fails at startup

## Architecture Standards

See [Architecture Standards](../04-references/architecture-standards/00-overview.md) for complete documentation.
