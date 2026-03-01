# AGENTS.md — AI Assistant Instructions

This file tells AI coding assistants how to work with this codebase.
For full details, see `docs/99-reference-architecture/`.

## Project Overview

BFF (Backend-for-Frontend) Python web application skeleton.
FastAPI backend, React frontend, PostgreSQL, Redis, Taskiq.

## Critical Rules

- **No hardcoded values.** All configuration from `config/settings/*.yaml`. All secrets from `config/.env`. No hardcoded fallbacks in code, ever.
- **Absolute imports only.** Always `from modules.backend.core.config import ...`. Never relative imports.
- **Centralized logging only.** Always `from modules.backend.core.logging import get_logger`. Never `import logging` directly.
- **Timezone-naive UTC datetimes.** Use `from modules.backend.core.utils import utc_now`. Never `datetime.utcnow()` (deprecated) or `datetime.now()` (local time).
- **`.project_root` marker** determines the project root. Use `find_project_root()` from `modules.backend.core.config`.
- **All CLI scripts must have `--verbose` and `--debug` options** with appropriate logging for each.
- **Files must not exceed 1000 lines.** Target ~400-500 lines. Split into focused submodules if larger.
- **`__init__.py` files must be minimal.** Docstring and necessary exports only. No business logic.
- **Secure by default (P8).** All external interfaces deny access when unconfigured. Empty allowlists = deny all. Missing secrets = startup failure. New channels/features disabled by default.

## Architecture

### Layered Backend (strict — no skipping layers)

```
API Layer (modules/backend/api/)         → HTTP handlers, request/response
Service Layer (modules/backend/services/) → Business logic, orchestration
Repository Layer (modules/backend/repositories/) → Data access, queries
Model Layer (modules/backend/models/)     → SQLAlchemy entities
```

### Configuration

- Secrets (passwords, tokens, keys): `config/.env` via Pydantic Settings
- Application settings: `config/settings/*.yaml` via `get_app_config()`
- Access in code: `from modules.backend.core.config import get_settings, get_app_config`

### Entry Points

- `cli.py` — Click-based CLI (--service server|worker|scheduler|event-worker|health|config|test|migrate|info --action start|stop|restart|status)
- `modules/backend/main.py` — FastAPI application (for uvicorn)
- `cli.py --service event-worker` — FastStream consumer (Redis Streams)

### Key Modules

| Module | Purpose |
|--------|---------|
| `modules/backend/core/config.py` | Configuration loading (YAML + .env) |
| `modules/backend/core/logging.py` | Centralized structured logging (structlog → logs/system.jsonl) |
| `modules/backend/core/exceptions.py` | Custom exception hierarchy |
| `modules/backend/core/middleware.py` | Request context (X-Request-ID, X-Frontend-ID → source field) |
| `modules/backend/core/database.py` | Async SQLAlchemy engine and sessions |
| `modules/backend/core/security.py` | JWT, password hashing, API keys |
| `modules/backend/core/utils.py` | Utilities (utc_now) |
| `modules/backend/core/config_schema.py` | Pydantic schemas for YAML config validation |
| `modules/backend/core/concurrency.py` | Thread/process pools, semaphores, `TracedThreadPoolExecutor`, `get_interpreter_pool()` (3.14+) |
| `modules/backend/core/resilience.py` | Circuit breaker, retry callbacks, resilience patterns |
| `modules/backend/events/broker.py` | FastStream RedisBroker setup and factory |
| `modules/backend/events/schemas.py` | `EventEnvelope` base and note domain events |
| `modules/backend/events/publishers.py` | `NoteEventPublisher` (Redis Streams) |
| `modules/backend/events/consumers/notes.py` | Note event consumer with resilience stack + DLQ |
| `modules/backend/tasks/broker.py` | Taskiq broker (Redis backend) |
| `modules/backend/agents/` | Agent coordinator and vertical agents (PydanticAI) |
| `modules/backend/gateway/` | Channel adapter registry and security (rate limiting, startup checks) |
| `modules/telegram/` | Telegram bot (aiogram v3, webhook mode) |
| `modules/frontend/` | React + Vite + Tailwind |

## Code Patterns

### Error Handling

```python
from modules.backend.core.exceptions import NotFoundError, ValidationError
```

Raise domain exceptions in services. Exception handlers in `core/exception_handlers.py` convert to HTTP responses.

### Logging

```python
from modules.backend.core.logging import get_logger
logger = get_logger(__name__)
logger.info("Operation completed", extra={"task_id": task.id, "duration": elapsed})
```

### Database Sessions

```python
from modules.backend.core.dependencies import DbSession

@router.get("/items")
async def get_items(db: DbSession):
    ...
```

### Background Tasks

```python
from modules.backend.tasks.broker import get_broker
broker = get_broker()
```

### Concurrency

```python
from modules.backend.core.concurrency import get_io_pool, get_cpu_pool, get_semaphore

# Run blocking I/O in thread pool (preserves structlog context + OTel spans)
result = await loop.run_in_executor(get_io_pool(), blocking_fn, arg)

# On Python 3.14+: optional interpreter pool (sub-interpreters, lower startup than process pool)
interp = get_interpreter_pool()
if interp is not None:
    result = await loop.run_in_executor(interp, cpu_fn, arg)
else:
    result = await loop.run_in_executor(get_cpu_pool(), cpu_fn, arg)

# Limit concurrent access to external services
async with get_semaphore("database"):
    result = await db.execute(query)
```

**Debugging (Python 3.14+):** To inspect stuck async tasks in a running process: `python -m asyncio pstree <PID>` (built-in, no install).

### Resilience

Stack order: Circuit Breaker → Retry → Semaphore → Timeout → Call.

```python
from modules.backend.core.resilience import create_circuit_breaker, log_retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

breaker = create_circuit_breaker("redis", fail_max=5, timeout_duration=30)

@breaker
@retry(stop=stop_after_attempt(3), wait=wait_exponential(), before_sleep=log_retry, reraise=True)
async def call_external():
    async with asyncio.timeout(10):
        ...
```

### Event Publishing

```python
from modules.backend.events.publishers import NoteEventPublisher

publisher = NoteEventPublisher()
await publisher.note_created(note_id="123", title="Hello", correlation_id=request_id)
```

Feature-flag gated: `events_publish_enabled` in `config/settings/features.yaml`.

## Testing

- `tests/unit/` — fast, mocked, no external dependencies
- `tests/integration/` — real database
- `tests/e2e/` — full stack
- Framework: pytest with pytest-asyncio
- Run: `pytest tests/unit -v`

## What NOT to Do

- Do not create helper or wrapper scripts (except in `scripts/`)
- Do not add business logic to `__init__.py` files
- Do not use `os.getenv()` with fallback defaults
- Do not create standalone loggers with `logging.getLogger()`
- Do not use relative imports
- Do not use `datetime.now()` or `datetime.utcnow()`
- Do not hardcode URLs, ports, timeouts, or any configurable value
- Do not skip layers (API calling repository directly)

## Reference Architecture

Full standards in `docs/99-reference-architecture/`. Documents are organized by category:
- **`01–18` Core** (`*-core-*.md`) — apply to all projects
- **`20–27` Optional** (`*-opt-*.md`) — adopt per project need
- **`30–35` AI** (`*-ai-*.md`) — AI/agentic capabilities

### Core Standards (01–18)

| Doc | Topic |
|-----|-------|
| 01-core-overview | Architecture overview and document index |
| 02-core-principles | Non-negotiable architectural mandates |
| 03-core-primitive-identification | Identifying the system's fundamental data type |
| 04-core-backend-architecture | Backend framework, service layer, API design |
| 05-core-module-structure | Module organization and inter-module communication |
| 06-core-authentication | Authentication and authorization |
| 07-core-python-coding-standards | Python file organization, imports, CLI, error handling |
| 08-core-observability | Logging, metrics, distributed tracing, profiling |
| 09-core-development-workflow | Git workflow, CI/CD, versioning |
| 10-core-error-codes | Error code registry |
| 11-core-project-template | Standard project directory structure |
| 12-core-testing-standards | Test organization, fixtures, coverage |
| 13-core-security-standards | Application security (OWASP, cryptography) |
| 14-core-data-protection | Data protection and privacy (PII, GDPR) |
| 15-core-background-tasks | Background tasks and scheduling (Taskiq) |
| 16-core-concurrency-and-resilience | Concurrency model, resilience patterns, Python 3.14 |
| 17-core-deployment-bare-metal | Self-hosted deployment (Ubuntu, systemd, nginx) |
| 18-core-deployment-azure | Azure managed services deployment |

### Optional Modules (20–27)

| Doc | Topic |
|-----|-------|
| 20-opt-data-layer | Advanced database, time-series, caching |
| 21-opt-event-architecture | Event-driven communication (FastStream, Redis Streams) |
| 22-opt-frontend-architecture | React web frontend |
| 23-opt-typescript-coding-standards | TypeScript/React coding standards |
| 24-opt-telegram-bot-integration | Telegram bot (aiogram v3, webhook) |
| 25-opt-telegram-client-integration | Telegram Client API (MTProto) |
| 26-opt-tui-architecture | Terminal UI (Textual) |
| 27-opt-multi-channel-gateway | Multi-channel delivery, sessions, WebSocket |

### AI Modules (30–35)

| Doc | Topic |
|-----|-------|
| 30-ai-llm-integration | LLM provider layer, prompts, cost tracking |
| 31-ai-agentic-architecture | Agentic AI conceptual architecture |
| 32-ai-agentic-pydanticai | Agentic AI PydanticAI implementation |
| 33-ai-agent-first-infrastructure | MCP, A2A, agent identity, intent APIs |
| 34-ai-ai-first-interface-design | AI-first service factory, discovery endpoints |
| 35-ai-event-session-architecture | Event-driven sessions, plans, memory, approvals |
