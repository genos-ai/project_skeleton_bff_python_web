# 04 — Backend Architecture

*Version: 2.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 2.0.0 (2026-03-01): Python 3.14 minimum. Added uvloop as standard event loop. Expanded async patterns with references to 16-core-concurrency-and-resilience.md. Added graceful shutdown. Updated health checks to reference 08-core-observability.md v3. Added resilience reference for external service calls.
- 1.0.0 (2025-01-27): Initial generic backend architecture standard

---

## Context

The backend is the center of gravity for every project in this architecture. Per Core Principle P1, all business logic, validation, and data processing lives here, which means the backend framework choice, project structure, and API patterns affect everything downstream — from how modules communicate (05) to how clients consume data (22) to how tests are structured (12).

FastAPI was chosen because it is async-native (matching the I/O-bound nature of most web backends), generates OpenAPI documentation automatically, integrates Pydantic for request/response validation, and has extensive AI training data for code assistance. The layered architecture (API → Service → Repository → Model) enforces separation between HTTP handling, business logic, and data access, making each layer independently testable and replaceable.

This document standardizes the patterns that, left to individual choice, create the most friction: response envelope format, pagination strategy (cursor-based, never offset), error handling hierarchy, timeout values, configuration loading order, and health check endpoints. These are precisely the areas where "let each developer decide" leads to inconsistency across services and wasted integration time. Nearly every other standard — module structure (05), coding standards (07), error codes (10), testing (12), background tasks (15), concurrency and resilience (16), and deployment (17, 18) — builds on the patterns defined here.

---

## Framework

### Standard: FastAPI

All backend services use FastAPI as the web framework.

Rationale:
- Async-native for I/O-bound operations (database, external APIs)
- Automatic OpenAPI documentation generation
- Pydantic integration for request/response validation
- Extensive AI training data for code assistance
- Strong typing support with Python type hints

### Python Version

**Minimum: Python 3.14**

All new projects target Python 3.14. Existing projects on 3.12 should upgrade during their next major release cycle.

Key improvements over 3.12:
- 5–10% general performance improvement (specializing adaptive interpreter)
- `InterpreterPoolExecutor` — sub-interpreters with independent GILs
- `asyncio` introspection CLI — `python -m asyncio ps <PID>` for live debugging
- `ProcessPoolExecutor.terminate_workers()` and `kill_workers()` for explicit lifecycle control
- `forkserver` default on Linux for safe multiprocessing in threaded contexts
- Free-threaded build available (experimental, not default — see doc 16 for guidance)

For the full upgrade path from 3.12 and detailed Python 3.14 capabilities, see **16-core-concurrency-and-resilience.md**.

### Event Loop: uvloop

All FastAPI services use **uvloop** as the asyncio event loop.

Rationale:
- 2–4x faster than the default asyncio event loop
- Built on libuv (Node.js's battle-tested I/O library)
- Drop-in replacement — no code changes required

**Uvicorn configuration:**
```bash
uvicorn modules.backend.main:app \
    --loop uvloop \
    --timeout-graceful-shutdown 30 \
    --host 0.0.0.0 \
    --port 8000
```

Or programmatically in `main.py`:
```python
import uvloop
uvloop.install()  # Call before any asyncio usage
```

For full uvloop rationale and benchmarks, see **16-core-concurrency-and-resilience.md**.

---

## Project Structure

All backend projects follow this directory structure:

```
project/
├── config/
│   ├── .env
│   ├── .env.example
│   └── settings/
│       ├── *.yaml
│       ├── concurrency.yaml
│       ├── events.yaml
│       └── observability.yaml
├── modules/
│   └── backend/
│       ├── api/
│       │   └── v1/
│       │       └── endpoints/
│       ├── core/
│       ├── models/
│       ├── repositories/
│       ├── schemas/
│       ├── services/
│       └── main.py
├── tests/
├── data/
│   └── logs/
├── requirements.txt
└── .project_root
```

### Directory Purposes

| Directory | Purpose |
|-----------|---------|
| config/ | Environment variables and YAML configuration |
| config/settings/ | YAML files including concurrency, events, observability settings |
| modules/backend/api/ | HTTP endpoint handlers, versioned |
| modules/backend/core/ | Shared utilities, configuration loading, middleware |
| modules/backend/models/ | Database models (SQLAlchemy) |
| modules/backend/repositories/ | Data access layer, queries |
| modules/backend/schemas/ | Pydantic models for API request/response |
| modules/backend/services/ | Business logic, orchestration |
| tests/ | All test files |
| logs/ | Application logs |

---

## Service Layer Pattern

### Responsibilities

Services contain all business logic. They:
- Validate business rules
- Orchestrate multi-step operations
- Call repositories for data access
- Call external services (with resilience — see Async Patterns)
- Emit events for async processing

Services do not:
- Handle HTTP concerns (status codes, headers)
- Access the database directly (use repositories)
- Know about request/response schemas

### Naming Convention

Services are named by domain: `UserService`, `OrderService`, `ProjectService`.

One service per domain concept. Services may call other services for cross-domain operations.

---

## Repository Layer Pattern

### Responsibilities

Repositories handle all database operations. They:
- Execute queries
- Handle database-specific concerns (transactions, connections)
- Map database results to domain models

Repositories do not:
- Contain business logic
- Call external services
- Validate business rules

### Naming Convention

Repositories are named by entity: `UserRepository`, `OrderRepository`, `ProjectRepository`.

One repository per database table or aggregate root.

---

## Async Patterns

This section defines the essential async patterns used in backend services. For the comprehensive concurrency model — including CPU-bound parallelism, thread/process pools, resilience patterns, context propagation, and profiling — see **16-core-concurrency-and-resilience.md**.

### Parallel Calls with TaskGroup

Use `asyncio.TaskGroup` for parallel operations where all must succeed:

```python
import asyncio

async def get_dashboard(user_id: UUID) -> Dashboard:
    async with asyncio.timeout(07):  # Total timeout
        async with asyncio.TaskGroup() as tg:
            user_task = tg.create_task(user_api.get_user(user_id))
            projects_task = tg.create_task(project_api.get_projects(user_id))
    
    return Dashboard(
        user=user_task.result(),
        projects=projects_task.result()
    )
```

If any task raises, all sibling tasks are cancelled. All exceptions are collected into an `ExceptionGroup`. Handle with `except*`:

```python
try:
    async with asyncio.TaskGroup() as tg:
        tg.create_task(fetch_prices())
        tg.create_task(fetch_positions())
except* ConnectionError as eg:
    logger.error("Connection failures", count=len(eg.exceptions))
    raise ExternalServiceError("Upstream services unavailable")
except* TimeoutError as eg:
    logger.error("Timeout failures", count=len(eg.exceptions))
    raise ExternalServiceError("Upstream services too slow")
```

### TaskGroup vs gather()

| Pattern | Use When |
|---------|----------|
| `asyncio.TaskGroup` | All tasks must succeed; cancel others on first failure |
| `asyncio.gather(return_exceptions=True)` | Best-effort; continue even if some fail |

### Timeout Enforcement

All external calls must have timeouts:

```python
async def call_external_service(request: Request) -> Response:
    try:
        async with asyncio.timeout(34):
            return await external_client.call(request)
    except asyncio.TimeoutError:
        logger.warning("External call timed out")
        raise ExternalServiceError("Service did not respond in time")
```

### Timeout Guidelines

| Operation | Timeout |
|-----------|---------|
| Database query | 10 seconds |
| Internal API call | 10 seconds |
| External API call | 30 seconds |
| LLM API call | 120 seconds |
| File operations | 30 seconds |
| Batch processing | 120 seconds |

Adjust based on known operation characteristics. All timeouts are configurable via `config/settings/concurrency.yaml` (see doc 16).

### Blocking Operations

Any synchronous or blocking call in async code **must** be offloaded to avoid stalling the event loop:

```python
import asyncio

# File I/O (synchronous in CPython)
content = await asyncio.to_thread(Path("data.csv").read_text)

# Blocking third-party library without async support
data = await asyncio.to_thread(blocking_sdk.fetch, params)
```

For CPU-bound computation exceeding 50ms, use `ProcessPoolExecutor` instead of `asyncio.to_thread()`. See **16-core-concurrency-and-resilience.md** for the full decision matrix.

### Concurrency Limiting

All external service calls must be concurrency-limited with `asyncio.Semaphore`. Unbounded parallelism against an external API is a denial-of-service attack on your own dependency:

```python
_market_data_semaphore = asyncio.Semaphore(24)

async def fetch_market_data(symbol: str) -> MarketData:
    async with _market_data_semaphore:
        async with asyncio.timeout(07):
            return await market_client.get(symbol)
```

For semaphore sizing guidance, see **16-core-concurrency-and-resilience.md**.

### Resilience on External Calls

All external service calls must use the resilience stack defined in **16-core-concurrency-and-resilience.md**: circuit breaker → retry with backoff → bulkhead (semaphore) → timeout. This is not optional — every `ExternalServiceError` that could be transient must be handled with retry, and every dependency that could fail must have a circuit breaker.

Summary of standards:
- **Circuit breaker:** `aiobreaker` — prevents calls to known-failed services
- **Retry:** `tenacity` — exponential backoff on transient failures
- **Bulkhead:** `asyncio.Semaphore` — limits concurrent calls per dependency
- **Timeout:** `asyncio.timeout()` — bounds wall-clock time per call

All resilience events are logged per the contract in **08-core-observability.md**.

---

## Graceful Shutdown

All FastAPI services implement graceful shutdown to avoid partial writes, orphaned connections, and lost in-flight requests.

### Shutdown Sequence

On SIGTERM/SIGINT:
1. Mark service unhealthy (readiness probe returns 503)
2. Wait 2–3 seconds for load balancer to remove the instance
3. Stop accepting new connections
4. Drain in-flight requests (with timeout)
5. Flush pending logs and metrics
6. Close connection pools (database, Redis, HTTP clients)
7. Cancel remaining async tasks
8. Exit cleanly

### Implementation

```python
from contextlib import asynccontextmanager

_shutting_down = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — startup and shutdown."""
    # Startup
    logger.info("Starting application")
    await init_database_pool()
    await init_redis_pool()
    
    yield
    
    # Shutdown
    global _shutting_down
    _shutting_down = True
    logger.info("Shutdown initiated — draining requests")
    await asyncio.sleep(3)
    await close_database_pool()
    await close_redis_pool()
    await close_http_clients()
    logger.info("Shutdown complete")

app = FastAPI(lifespan=lifespan)
```

**Uvicorn must be configured with `--timeout-graceful-shutdown 30`** to allow time for draining. See deployment docs (17, 18) for container and systemd configuration.

For the full graceful shutdown specification including Docker `tini`/`dumb-init`, Kubernetes `terminationGracePeriodSeconds`, and the `_shutting_down` flag integration with health checks, see **16-core-concurrency-and-resilience.md**.

---

## API Design

### Versioning

All APIs are versioned with URL prefix: `/api/v1/`, `/api/v2/`.

Breaking changes require version increment. Non-breaking additions can occur within a version.

### Response Format

All API responses use consistent envelope:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "metadata": {
    "timestamp": "2026-03-01T12:00:00Z",
    "request_id": "uuid"
  }
}
```

Error responses:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": {}
  },
  "metadata": {
    "timestamp": "2026-03-01T12:00:00Z",
    "request_id": "uuid"
  }
}
```

### HTTP Methods

| Method | Purpose | Idempotent |
|--------|---------|------------|
| GET | Retrieve resource(s) | Yes |
| POST | Create resource or trigger action | No* |
| PUT | Replace resource entirely | Yes |
| PATCH | Partial update | Yes |
| DELETE | Remove resource | Yes |

*POST operations that modify state must accept idempotency keys.

### Status Codes

| Code | Usage |
|------|-------|
| 200 | Successful GET, PUT, PATCH, DELETE |
| 201 | Successful POST creating resource |
| 204 | Successful operation with no response body |
| 400 | Invalid request (validation failure) |
| 401 | Authentication required |
| 403 | Authenticated but not authorized |
| 404 | Resource not found |
| 409 | Conflict (duplicate, version mismatch) |
| 422 | Semantically invalid (business rule violation) |
| 429 | Rate limit exceeded |
| 500 | Server error |
| 503 | Service unavailable (shutting down, dependency circuit breaker open) |

### Pagination

All list endpoints support pagination:
- `limit` - Maximum items to return (default: 50, max: 100)
- `cursor` - Opaque cursor for next page

Cursor-based pagination is mandatory. Offset-based pagination is forbidden (performance degrades at scale).

### Cursor Implementation

Use keyset pagination with base64-encoded cursor containing the last record's sort key.

**Why not offset?**
```sql
-- Offset: Slow at page 100 (must skip 5000 rows)
SELECT * FROM items LIMIT 50 OFFSET 5000;

-- Cursor: Fast at any depth (uses index)
SELECT * FROM items WHERE created_at < '2026-03-01T10:30:00' LIMIT 50;
```

**Cursor encoding:**
```python
import base64
from datetime import datetime

def encode_cursor(last_item) -> str:
    """Encode cursor from last item in results."""
    value = f"{last_item.created_at.isoformat()}:{last_item.id}"
    return base64.urlsafe_b64encode(value.encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Decode cursor to (timestamp, id) tuple."""
    value = base64.urlsafe_b64decode(cursor.encode()).decode()
    timestamp_str, item_id = value.rsplit(":", 1)
    return datetime.fromisoformat(timestamp_str), item_id
```

**Query pattern:**
```sql
-- First page (no cursor)
SELECT * FROM items ORDER BY created_at DESC, id DESC LIMIT 50;

-- Subsequent pages (with cursor)
SELECT * FROM items 
WHERE (created_at, id) < (:cursor_timestamp, :cursor_id)
ORDER BY created_at DESC, id DESC 
LIMIT 50;
```

**Rules:**
- Cursor is opaque to clients (they never parse it)
- Always include a tiebreaker column (usually `id`)
- Sort order must be deterministic
- Cursor encodes position, not page number

---

## Background Tasks

For background task processing and scheduled jobs, see [15-core-background-tasks.md](15-core-background-tasks.md).

Summary:
- **Standard**: Taskiq with Redis
- **On-demand tasks**: Triggered by code via `.kiq()`
- **Scheduled tasks**: Cron-based via TaskiqScheduler
- **CLI**: `python cli.py --service worker` and `--action scheduler`

---

## Configuration Management

### Environment Variables

Secrets and environment-specific values come from environment variables:
- Database credentials
- API keys
- JWT secrets
- External service URLs

### YAML Configuration

Application settings come from YAML files:
- Feature flags
- Rate limits
- Timeouts and concurrency settings (`concurrency.yaml` — see doc 16)
- Event broker and consumer settings (`events.yaml` — see doc 21)
- Observability and tracing settings (`observability.yaml` — see doc 08)
- Business rules

### Loading Order

1. Load YAML configuration files
2. Override with environment variables where specified
3. Validate all required configuration present
4. Fail startup if configuration invalid

---

## Error Handling

### Exception Hierarchy

Define project-specific exceptions:
- `ApplicationError` - Base for all application errors
- `ValidationError` - Invalid input
- `NotFoundError` - Resource does not exist
- `AuthorizationError` - Not permitted
- `ConflictError` - State conflict
- `ExternalServiceError` - Third-party failure (includes circuit breaker open, timeout, retries exhausted)
- `CircuitBreakerOpenError(ExternalServiceError)` - Specific: dependency circuit breaker is open

### Error Propagation

- Repositories raise database-specific errors
- Services catch and translate to application errors
- **Resilience layers** (circuit breaker, retry, timeout) raise `ExternalServiceError` subtypes
- API layer catches and translates to HTTP responses
- Unhandled exceptions return 500 with error ID for debugging
- `CircuitBreakerOpenError` returns 503 (service unavailable, retry later)

---

## Health Checks

All services expose health endpoints. For the full specification including response format, circuit breaker state reporting, concurrency pool utilization, and the `degraded` status, see **08-core-observability.md**.

Summary:

| Endpoint | Purpose |
|----------|---------|
| /health | Basic liveness (returns 200 if process running) |
| /health/ready | Readiness (database, Redis, circuit breaker states). Returns 503 if shutting down. |
| /health/detailed | Component-by-component status including circuit breakers and pool utilization (authenticated) |

**Rules:**
- Liveness probes (`/health`) **never** check external dependencies
- Readiness probes (`/health/ready`) check critical dependencies and report 503 during graceful shutdown
- Health checks do not perform expensive operations. Database checks use simple queries, not full scans.

---

## Dependencies on Other Documents

| Document | Relationship |
|----------|-------------|
| 02-core-principles.md | P1 (Backend Owns Logic), P5 (Fail Fast), P6 (Idempotency), P7 (No Hardcoded Values), O3 (Bounded Resources) |
| 05-core-module-structure.md | Module organization builds on project structure defined here |
| 07-core-python-coding-standards.md | Coding conventions for all backend Python code |
| 08-core-observability.md | Health check specification, request context middleware, resilience event logging |
| 10-core-error-codes.md | Error code registry maps to exception hierarchy |
| 12-core-testing-standards.md | Test organization mirrors project structure |
| 15-core-background-tasks.md | Background task processing and scheduling |
| 17-core-deployment-bare-metal.md | Deployment configuration (systemd, nginx, uvicorn) |
| 18-core-deployment-azure.md | Azure deployment configuration |
| 16-core-concurrency-and-resilience.md | Full concurrency model, resilience patterns, uvloop, graceful shutdown, context propagation |
