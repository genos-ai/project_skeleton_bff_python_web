# Implementation Plan: Concurrency, Events, and Observability Infrastructure

*Created: 2026-03-01*
*Status: Implemented*
*Reference Docs: 08-core-observability, 16-core-concurrency-and-resilience, 21-opt-event-architecture*

---

## Progress Tracker

| # | Task | File(s) Affected | Status |
|---|------|-----------------|--------|
| 1 | Git commit and create feature branch | — | Done |
| 2 | Add new dependencies to `requirements.txt` | `requirements.txt` | Done |
| 3 | Create `config/settings/observability.yaml` | `config/settings/observability.yaml` | Done |
| 4 | Create `config/settings/concurrency.yaml` | `config/settings/concurrency.yaml` | Done |
| 5 | Create `config/settings/events.yaml` | `config/settings/events.yaml` | Done |
| 6 | Add Pydantic schemas for the three new YAML files | `modules/backend/core/config_schema.py` | Done |
| 7 | Register new configs in `AppConfig` and `config.py` | `modules/backend/core/config.py` | Done |
| 8 | Add feature flags for events and observability | `config/settings/features.yaml`, `config_schema.py` | Done |
| 9 | Update `VALID_SOURCES` and add `add_trace_context` processor | `modules/backend/core/logging.py` | Done |
| 10 | Update middleware default source to `"unknown"` | `modules/backend/core/middleware.py` | Done |
| 11 | Create `core/concurrency.py` — pools, semaphores, `TracedThreadPoolExecutor` | `modules/backend/core/concurrency.py` | Done |
| 12 | Create `core/resilience.py` — `ResilienceLogger`, tenacity callback, composed stack | `modules/backend/core/resilience.py` | Done |
| 13 | Update `main.py` lifespan — graceful shutdown, pool cleanup, OTel/metrics hooks | `modules/backend/main.py` | Done |
| 14 | Update health checks — `TaskGroup`, circuit breaker/pool status, degraded state | `modules/backend/api/health.py` | Done |
| 15 | Create `events/__init__.py` | `modules/backend/events/__init__.py` | Done |
| 16 | Create `events/broker.py` — FastStream RedisBroker setup | `modules/backend/events/broker.py` | Done |
| 17 | Create `events/schemas.py` — `EventEnvelope` and note domain events | `modules/backend/events/schemas.py` | Done |
| 18 | Create `events/middleware.py` — `ObservabilityMiddleware` for consumers | `modules/backend/events/middleware.py` | Done |
| 19 | Create `events/publishers.py` — `NoteEventPublisher` | `modules/backend/events/publishers.py` | Done |
| 20 | Create `events/consumers/notes.py` — note event consumer with resilience stack | `modules/backend/events/consumers/notes.py` | Done |
| 21 | Create `events/consumers/__init__.py` | `modules/backend/events/consumers/__init__.py` | Done |
| 22 | Wire `NoteEventPublisher` into `NoteService` | `modules/backend/services/note.py` | Done |
| 23 | Add `--service event-worker` to CLI | `cli.py` | Done |
| 24 | Write unit tests for `core/concurrency.py` | `tests/unit/backend/core/test_concurrency.py` | Done |
| 25 | Write unit tests for `core/resilience.py` | `tests/unit/backend/core/test_resilience.py` | Done |
| 26 | Write unit tests for event schemas and publisher | `tests/unit/backend/events/test_events.py` | Done |
| 27 | Write unit tests for event consumer | `tests/unit/backend/events/test_consumers.py` | Done |
| 28 | Update integration tests for health endpoint enhancements | `tests/integration/backend/api/test_health_enhanced.py` | Done |
| 29 | Run full test suite — 436 passed, zero failures | All test files | Done |
| 30 | Update `AGENTS.md` — document new modules | `AGENTS.md` | Done |
| 31 | Merge branch back to main | — | Pending |

---

## Background

The reference architecture has been significantly updated with three major infrastructure additions:

1. **Concurrency and Resilience** (doc 16) — now a core standard requiring `uvloop`, `asyncio.TaskGroup`, composed resilience stacks (circuit breaker + retry + semaphore + timeout), `TracedThreadPoolExecutor`, and graceful shutdown via lifespan.

2. **Observability** (doc 08) — adds distributed tracing hooks (OpenTelemetry), metrics hooks (Prometheus), resilience event logging, context propagation across threads/processes/tasks, and a telemetry debug API.

3. **Event Architecture** (doc 21) — adds FastStream with Redis Streams as an event bus, standardized `EventEnvelope` schema, consumer resilience, dead letter queues, and observability middleware.

This plan implements all three as **skeleton infrastructure** — the patterns, interfaces, and a working end-to-end example — so that other AIs and developers can reference the patterns when building features.

The event-driven example extends the existing Notes domain: when a note is created, updated, or archived, the service publishes an event to Redis Streams, and an example consumer processes it.

### Design Principles

- All new features are **disabled by default** via feature flags (P8: Secure by Default)
- All new config goes in YAML files — no hardcoded values
- New modules follow the same patterns as existing code (structlog, absolute imports, `get_logger`)
- The event system is **complementary to Taskiq**, not a replacement
- OTel and Prometheus are **hook-only** in the skeleton — the exporters are wired but disabled by default
- Every new module has unit tests

### What Is NOT In Scope

- Full OpenTelemetry Collector / Jaeger / Tempo infrastructure
- Prometheus server / Grafana dashboards
- Session architecture (doc 35) — that is Tier 3/4, this skeleton is Tier 1/2
- `InterpreterPoolExecutor` examples (3.14 feature, evaluate later)
- Shared memory / numpy patterns (domain-specific)
- Transactional outbox (requires migration, more complexity than skeleton needs)
- Telemetry debug API (depends on auth system, out of scope for skeleton)
- Python 3.14 is now the project minimum (pyproject.toml requires-python >=3.14).

---

## Architecture

### New Module Structure

```
modules/backend/
├── core/
│   ├── concurrency.py      ← NEW: pools, semaphores, TracedThreadPoolExecutor
│   ├── resilience.py        ← NEW: ResilienceLogger, tenacity callback, composed stack
│   ├── config.py            ← MODIFIED: load 3 new YAML configs
│   ├── config_schema.py     ← MODIFIED: schemas for 3 new YAML files
│   ├── logging.py           ← MODIFIED: add_trace_context, VALID_SOURCES update
│   ├── middleware.py         ← MODIFIED: default source "unknown"
│   └── ...
├── events/                   ← NEW: entire module
│   ├── __init__.py
│   ├── broker.py            ← FastStream RedisBroker setup
│   ├── schemas.py           ← EventEnvelope + note domain events
│   ├── middleware.py         ← ObservabilityMiddleware for consumers
│   ├── publishers.py        ← NoteEventPublisher
│   └── consumers/
│       ├── __init__.py
│       └── notes.py         ← Note event consumer with resilience
├── api/
│   └── health.py            ← MODIFIED: TaskGroup, CB/pool status
├── services/
│   └── note.py              ← MODIFIED: publish events after mutations
└── main.py                   ← MODIFIED: lifespan, pool cleanup
```

### Data Flow: Event-Driven Example

```
POST /api/v1/notes
  │
  ▼
NoteService.create_note()
  │
  ├── NoteRepository.create()  →  PostgreSQL
  │
  └── NoteEventPublisher.note_created(note)
        │
        ▼
      Redis Stream "notes:note-created"
        │
        ▼
      Consumer (event-worker process)
        │
        ├── ObservabilityMiddleware (bind structlog context, measure duration)
        │
        └── handle_note_created(event)
              │
              ├── Circuit Breaker (aiobreaker)
              │     └── Retry (tenacity, 3 attempts)
              │           └── Timeout (asyncio.timeout)
              │                 └── Process event (log, example downstream action)
              │
              └── On failure after retries → DLQ (dlq:notes:note-created)
```

### Resilience Stack (Applied Everywhere)

```
Circuit Breaker (aiobreaker)       ← Prevents calls to known-failed dependencies
  └── Retry (tenacity)             ← Handles transient failures with backoff
        └── Semaphore              ← Limits concurrent calls per dependency
              └── Timeout          ← Bounds wall-clock time
                    └── Actual Call
```

---

## Detailed Implementation Steps

### Step 1: Git Commit and Create Feature Branch

```bash
git add -A && git commit -m "chore: checkpoint before concurrency/events/observability implementation"
git checkout -b feat/concurrency-events-observability
```

---

### Step 2: Add New Dependencies to `requirements.txt`

**File:** `requirements.txt`

Add the following sections. Insert after the existing `structlog` entry (line 45) in the "Logging & Observability" section, and add new sections:

**Add to "Logging & Observability" section (after `structlog>=24.1.0`):**

```
# --- Tracing (hooks only — disabled by default) ---
opentelemetry-api>=1.24.0
opentelemetry-sdk>=1.24.0
opentelemetry-instrumentation-fastapi>=0.45b0
opentelemetry-instrumentation-httpx>=0.45b0
# --- Metrics (hooks only — disabled by default) ---
prometheus-fastapi-instrumentator>=7.0.0
prometheus-client>=0.20.0
```

**Add a new section after "Logging & Observability":**

```
# =============================================================================
# Resilience
# =============================================================================
tenacity>=9.0.0
uvloop>=0.21.0; sys_platform != "win32"
```

**Add a new section after "Redis & Background Tasks":**

```
# =============================================================================
# Event Bus
# =============================================================================
faststream[redis]>=0.5.0
```

**Move `aiobreaker` from "Telegram Bot" section to a new "Resilience" section** (it is a cross-cutting dependency, not Telegram-specific). The line `aiobreaker>=1.2.0` (currently line 33) should be moved to sit with `tenacity` under the "Resilience" section.

**Final "Resilience" section should be:**

```
# =============================================================================
# Resilience
# =============================================================================
aiobreaker>=1.2.0
tenacity>=9.0.0
uvloop>=0.21.0; sys_platform != "win32"
```

---

### Step 3: Create `config/settings/observability.yaml`

**File:** `config/settings/observability.yaml` (NEW)

```yaml
# =============================================================================
# Observability Configuration
# =============================================================================
# Available options:
#   Controls tracing, metrics, and health check behavior.
#   Tracing and metrics are disabled by default — enable when
#   backend infrastructure (OTel Collector, Prometheus) is deployed.
# =============================================================================

# -----------------------------------------------------------------------------
# Distributed Tracing (OpenTelemetry)
# -----------------------------------------------------------------------------
tracing:
  enabled: false
  service_name: "bff-python"
  exporter: "otlp"
  otlp_endpoint: "http://localhost:4317"
  sample_rate: 1.0

# -----------------------------------------------------------------------------
# Metrics (Prometheus)
# -----------------------------------------------------------------------------
metrics:
  enabled: false

# -----------------------------------------------------------------------------
# Health Checks
# -----------------------------------------------------------------------------
health_checks:
  ready_timeout_seconds: 5
  detailed_auth_required: false
```

---

### Step 4: Create `config/settings/concurrency.yaml`

**File:** `config/settings/concurrency.yaml` (NEW)

```yaml
# =============================================================================
# Concurrency Configuration
# =============================================================================
# Available options:
#   Controls thread pool, process pool, and semaphore sizing.
#   These values are upper bounds — adjust based on deployment resources.
#
#   Semaphore sizing guidelines (from doc 16):
#     External REST API:  10-20
#     LLM provider:       3-10
#     Database:           match connection pool_size
#     Redis:              50-100
#     Internal services:  20-50
# =============================================================================

# -----------------------------------------------------------------------------
# Thread Pool (for blocking operations via asyncio.to_thread)
# -----------------------------------------------------------------------------
thread_pool:
  max_workers: 10

# -----------------------------------------------------------------------------
# Process Pool (for CPU-bound operations)
# -----------------------------------------------------------------------------
process_pool:
  max_workers: 4

# -----------------------------------------------------------------------------
# Semaphores (per-dependency concurrency limits)
# -----------------------------------------------------------------------------
semaphores:
  database: 50
  redis: 100
  external_api: 20
  llm: 5

# -----------------------------------------------------------------------------
# Graceful Shutdown
# -----------------------------------------------------------------------------
shutdown:
  drain_seconds: 30
```

---

### Step 5: Create `config/settings/events.yaml`

**File:** `config/settings/events.yaml` (NEW)

```yaml
# =============================================================================
# Event Architecture Configuration
# =============================================================================
# Available options:
#   Controls the FastStream event bus, stream sizing, and consumer behavior.
#   The event system requires Redis (same instance as Taskiq/caching).
#
#   Stream naming: {domain}:{event-type}  e.g. notes:note-created
#   Consumer group: {service-name}        e.g. note-processor
#   Event type field: domain.entity.action (dot notation)
# =============================================================================

# -----------------------------------------------------------------------------
# Broker
# -----------------------------------------------------------------------------
broker:
  type: "redis"

# -----------------------------------------------------------------------------
# Streams
# -----------------------------------------------------------------------------
streams:
  default_maxlen: 100000

# -----------------------------------------------------------------------------
# Consumers
# -----------------------------------------------------------------------------
consumers:
  note-processor:
    stream: "notes:note-created"
    group: "note-processor"
    criticality: "standard"
    circuit_breaker:
      fail_max: 5
      timeout_duration: 30
    retry:
      max_attempts: 3
      backoff_multiplier: 1
      backoff_max: 10
    processing_timeout: 30

# -----------------------------------------------------------------------------
# Dead Letter Queue
# -----------------------------------------------------------------------------
dlq:
  enabled: true
  stream_prefix: "dlq"
```

---

### Step 6: Add Pydantic Schemas for the Three New YAML Files

**File:** `modules/backend/core/config_schema.py`

**Append** the following sections after the existing `GatewaySchema` class (line 231). Do not modify any existing code.

```python
# =============================================================================
# observability.yaml
# =============================================================================


class TracingSchema(_StrictBase):
    enabled: bool
    service_name: str
    exporter: str
    otlp_endpoint: str
    sample_rate: float


class MetricsSchema(_StrictBase):
    enabled: bool


class HealthChecksSchema(_StrictBase):
    ready_timeout_seconds: int
    detailed_auth_required: bool


class ObservabilitySchema(_StrictBase):
    tracing: TracingSchema
    metrics: MetricsSchema
    health_checks: HealthChecksSchema


# =============================================================================
# concurrency.yaml
# =============================================================================


class ThreadPoolSchema(_StrictBase):
    max_workers: int


class ProcessPoolSchema(_StrictBase):
    max_workers: int


class SemaphoresSchema(_StrictBase):
    database: int
    redis: int
    external_api: int
    llm: int


class ShutdownSchema(_StrictBase):
    drain_seconds: int


class ConcurrencySchema(_StrictBase):
    thread_pool: ThreadPoolSchema
    process_pool: ProcessPoolSchema
    semaphores: SemaphoresSchema
    shutdown: ShutdownSchema


# =============================================================================
# events.yaml
# =============================================================================


class EventBrokerSchema(_StrictBase):
    type: str


class EventStreamsSchema(_StrictBase):
    default_maxlen: int


class ConsumerCircuitBreakerSchema(_StrictBase):
    fail_max: int
    timeout_duration: int


class ConsumerRetrySchema(_StrictBase):
    max_attempts: int
    backoff_multiplier: int
    backoff_max: int


class ConsumerConfigSchema(_StrictBase):
    stream: str
    group: str
    criticality: str
    circuit_breaker: ConsumerCircuitBreakerSchema
    retry: ConsumerRetrySchema
    processing_timeout: int


class EventDlqSchema(_StrictBase):
    enabled: bool
    stream_prefix: str


class EventsSchema(_StrictBase):
    broker: EventBrokerSchema
    streams: EventStreamsSchema
    consumers: dict[str, ConsumerConfigSchema]
    dlq: EventDlqSchema
```

Also add the new schemas to the import list at the top of the file. The existing imports in `config.py` (step 7) will reference these by name.

---

### Step 7: Register New Configs in `AppConfig` and `config.py`

**File:** `modules/backend/core/config.py`

**7a.** Add the three new schema imports to the import block (lines 27-34). The current import is:

```python
from modules.backend.core.config_schema import (
    ApplicationSchema,
    DatabaseSchema,
    FeaturesSchema,
    GatewaySchema,
    LoggingSchema,
    SecuritySchema,
)
```

Replace with:

```python
from modules.backend.core.config_schema import (
    ApplicationSchema,
    ConcurrencySchema,
    DatabaseSchema,
    EventsSchema,
    FeaturesSchema,
    GatewaySchema,
    LoggingSchema,
    ObservabilitySchema,
    SecuritySchema,
)
```

**7b.** Add loading of the three new configs to `AppConfig.__init__` (lines 112-118). The current init is:

```python
def __init__(self) -> None:
    self._application = _load_validated(ApplicationSchema, "application.yaml")
    self._database = _load_validated(DatabaseSchema, "database.yaml")
    self._logging = _load_validated(LoggingSchema, "logging.yaml")
    self._features = _load_validated(FeaturesSchema, "features.yaml")
    self._security = _load_validated(SecuritySchema, "security.yaml")
    self._gateway = _load_validated(GatewaySchema, "gateway.yaml")
```

Replace with:

```python
def __init__(self) -> None:
    self._application = _load_validated(ApplicationSchema, "application.yaml")
    self._database = _load_validated(DatabaseSchema, "database.yaml")
    self._logging = _load_validated(LoggingSchema, "logging.yaml")
    self._features = _load_validated(FeaturesSchema, "features.yaml")
    self._security = _load_validated(SecuritySchema, "security.yaml")
    self._gateway = _load_validated(GatewaySchema, "gateway.yaml")
    self._observability = _load_validated(ObservabilitySchema, "observability.yaml")
    self._concurrency = _load_validated(ConcurrencySchema, "concurrency.yaml")
    self._events = _load_validated(EventsSchema, "events.yaml")
```

**7c.** Add three new properties to `AppConfig` after the existing `gateway` property (line 148):

```python
@property
def observability(self) -> ObservabilitySchema:
    """Observability settings (tracing, metrics, health checks)."""
    return self._observability

@property
def concurrency(self) -> ConcurrencySchema:
    """Concurrency settings (pools, semaphores, shutdown)."""
    return self._concurrency

@property
def events(self) -> EventsSchema:
    """Event architecture settings (broker, streams, consumers)."""
    return self._events
```

**7d.** Update the module docstring (lines 1-17) to add the three new YAML files to the settings list:

```
Settings (YAML):
    application.yaml   - App identity, server, cors, telegram, pagination
    database.yaml      - Database and Redis connection settings
    logging.yaml       - Logging configuration
    features.yaml      - Feature flags
    security.yaml      - JWT settings
    gateway.yaml       - Channel gateway configuration
    observability.yaml - Tracing, metrics, health check configuration
    concurrency.yaml   - Pool sizes, semaphores, shutdown timing
    events.yaml        - Event bus broker, streams, consumers
```

---

### Step 8: Add Feature Flags for Events and Observability

**File:** `config/settings/features.yaml`

Add the following entries. Insert after `experimental_background_tasks_enabled: true` (line 75):

```yaml

# -----------------------------------------------------------------------------
# Event Architecture (doc 21)
# -----------------------------------------------------------------------------
events_enabled: false
events_publish_enabled: false

# -----------------------------------------------------------------------------
# Observability Hooks (doc 08)
# -----------------------------------------------------------------------------
observability_tracing_enabled: false
observability_metrics_enabled: false
```

**File:** `modules/backend/core/config_schema.py`

Add these four fields to the `FeaturesSchema` class (after `experimental_background_tasks_enabled` at line 155):

```python
events_enabled: bool
events_publish_enabled: bool
observability_tracing_enabled: bool
observability_metrics_enabled: bool
```

---

### Step 9: Update `VALID_SOURCES` and Add `add_trace_context` Processor

**File:** `modules/backend/core/logging.py`

**9a.** Update `VALID_SOURCES` (lines 51-60). Replace the current frozenset:

```python
VALID_SOURCES = frozenset({
    "web",
    "cli",
    "tui",
    "mobile",
    "telegram",
    "api",
    "tasks",
    "internal",
})
```

With:

```python
VALID_SOURCES = frozenset({
    "web",
    "cli",
    "tui",
    "mobile",
    "telegram",
    "api",
    "tasks",
    "events",
    "internal",
    "agent",
    "unknown",
})
```

Three new values: `events` (event consumers), `agent` (autonomous agents), `unknown` (no X-Frontend-ID provided).

**9b.** Add the `add_trace_context` processor function. Insert after the `_resolve_log_path` function (after line 106) and before `setup_logging`:

```python
def add_trace_context(
    logger: Any, method_name: str, event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Structlog processor that adds OpenTelemetry trace context to log records.

    When tracing is enabled and a span is active, injects trace_id and span_id
    into every log record for correlation between logs and traces.

    No-ops gracefully when OpenTelemetry is not installed or no span is active.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except ImportError:
        pass
    return event_dict
```

**9c.** Insert the `add_trace_context` processor into the `shared_processors` list inside `setup_logging()`. The current list (lines 147-161) is:

```python
shared_processors: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    ...
]
```

Insert `add_trace_context` after `merge_contextvars` and before `add_log_level`:

```python
shared_processors: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    add_trace_context,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.UnicodeDecoder(),
    structlog.processors.CallsiteParameterAdder(
        parameters=[
            structlog.processors.CallsiteParameter.FUNC_NAME,
            structlog.processors.CallsiteParameter.LINENO,
        ],
    ),
]
```

**9d.** Update the module docstring (lines 7-16) to add `trace_id` and `span_id` to the structured fields list:

```
Structured fields in every JSON log record:
    timestamp   - ISO 8601 UTC timestamp
    level       - Log level (debug, info, warning, error, critical)
    logger      - Module path (e.g., modules.backend.core.middleware)
    event       - Log message
    func_name   - Function that emitted the log
    lineno      - Line number in source file
    source      - Origin context, set explicitly (web, cli, tui, telegram, events, agent, etc.)
    request_id  - Request correlation ID (when in HTTP request context)
    trace_id    - OpenTelemetry trace ID (when tracing is active)
    span_id     - OpenTelemetry span ID (when tracing is active)
```

---

### Step 10: Update Middleware Default Source to `"unknown"`

**File:** `modules/backend/core/middleware.py`

Change line 57. The current code is:

```python
raw_source = request.headers.get("X-Frontend-ID", "").lower().strip() or None
```

Replace with:

```python
raw_source = request.headers.get("X-Frontend-ID", "").lower().strip() or "unknown"
```

Also change line 63-64. The current code handles invalid source by setting to `None`:

```python
if raw_source is not None and raw_source not in VALID_SOURCES:
    logger.warning(
        "Invalid X-Frontend-ID header, ignoring",
        extra={"raw_source": raw_source, "valid_sources": sorted(VALID_SOURCES)},
    )
    raw_source = None
```

Replace with:

```python
if raw_source not in VALID_SOURCES:
    logger.warning(
        "Invalid X-Frontend-ID header, defaulting to unknown",
        extra={"raw_source": raw_source, "valid_sources": sorted(VALID_SOURCES)},
    )
    raw_source = "unknown"
```

Also update line 78. The current conditional check is:

```python
if raw_source is not None:
    context["source"] = raw_source
```

Replace with (source is always present now):

```python
context["source"] = raw_source
```

---

### Step 11: Create `core/concurrency.py`

**File:** `modules/backend/core/concurrency.py` (NEW, ~120 lines)

```python
"""
Concurrency Infrastructure.

Thread pool, process pool, and semaphore management for the application.
All pools are created lazily on first access and cleaned up during shutdown.

Pools:
    _io_pool    - TracedThreadPoolExecutor for blocking I/O (asyncio.to_thread replacement)
    _cpu_pool   - ProcessPoolExecutor for CPU-bound work

Semaphores:
    Created per-dependency to limit concurrent access to external services.
    Sizing is configured in config/settings/concurrency.yaml.

Usage:
    from modules.backend.core.concurrency import get_io_pool, get_cpu_pool, get_semaphore

    # Run blocking code in thread pool (preserves structlog context)
    result = await loop.run_in_executor(get_io_pool(), blocking_fn, arg)

    # Run CPU-bound code in process pool
    result = await loop.run_in_executor(get_cpu_pool(), cpu_fn, arg)

    # Limit concurrent access to external API
    async with get_semaphore("external_api"):
        result = await client.get(url)
"""

import asyncio
import contextvars
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_io_pool: ThreadPoolExecutor | None = None
_cpu_pool: ProcessPoolExecutor | None = None
_semaphores: dict[str, asyncio.Semaphore] = {}
_semaphore_capacities: dict[str, int] = {}


class TracedThreadPoolExecutor(ThreadPoolExecutor):
    """ThreadPoolExecutor that propagates contextvars to worker threads.

    Standard ThreadPoolExecutor does not carry structlog context, request_id,
    or OpenTelemetry spans into worker threads. This subclass copies the
    current context before dispatching, so all observability data is preserved.
    """

    def submit(self, fn, /, *args, **kwargs):
        ctx = contextvars.copy_context()
        return super().submit(ctx.run, fn, *args, **kwargs)


def get_io_pool() -> TracedThreadPoolExecutor:
    """Get the shared thread pool for blocking I/O operations.

    Creates the pool lazily on first call using config from concurrency.yaml.
    """
    global _io_pool
    if _io_pool is None:
        from modules.backend.core.config import get_app_config
        max_workers = get_app_config().concurrency.thread_pool.max_workers
        _io_pool = TracedThreadPoolExecutor(max_workers=max_workers)
        logger.info("Thread pool created", extra={"max_workers": max_workers})
    return _io_pool


def get_cpu_pool() -> ProcessPoolExecutor:
    """Get the shared process pool for CPU-bound operations.

    Creates the pool lazily on first call using config from concurrency.yaml.
    """
    global _cpu_pool
    if _cpu_pool is None:
        from modules.backend.core.config import get_app_config
        max_workers = get_app_config().concurrency.process_pool.max_workers
        _cpu_pool = ProcessPoolExecutor(max_workers=max_workers)
        logger.info("Process pool created", extra={"max_workers": max_workers})
    return _cpu_pool


def get_semaphore(name: str) -> asyncio.Semaphore:
    """Get a named semaphore for concurrency-limiting external calls.

    Semaphores are created lazily. The capacity is read from concurrency.yaml
    under `semaphores.<name>`. If the name is not configured, defaults to 20.
    """
    if name not in _semaphores:
        from modules.backend.core.config import get_app_config
        semaphore_config = get_app_config().concurrency.semaphores
        capacity = getattr(semaphore_config, name, 20)
        _semaphores[name] = asyncio.Semaphore(capacity)
        _semaphore_capacities[name] = capacity
        logger.debug("Semaphore created", extra={"name": name, "capacity": capacity})
    return _semaphores[name]


async def shutdown_pools() -> None:
    """Shut down all pools gracefully. Called during application shutdown.

    Pool shutdown is blocking, so we run it in a thread to avoid stalling
    the event loop during graceful shutdown.
    """
    global _io_pool, _cpu_pool

    if _io_pool is not None:
        await asyncio.to_thread(_io_pool.shutdown, wait=True)
        logger.info("Thread pool shut down")
        _io_pool = None

    if _cpu_pool is not None:
        await asyncio.to_thread(_cpu_pool.shutdown, wait=True)
        logger.info("Process pool shut down")
        _cpu_pool = None

    _semaphores.clear()
    _semaphore_capacities.clear()
    logger.debug("Semaphores cleared")
```

---

### Step 12: Create `core/resilience.py`

**File:** `modules/backend/core/resilience.py` (NEW, ~150 lines)

```python
"""
Resilience Infrastructure.

Circuit breaker listener, retry callback, and composed resilience patterns.
These are the building blocks referenced by doc 08 (observability) and
doc 16 (concurrency/resilience) for structured resilience event logging.

The composed resilience stack is always applied in this order (outside-in):
    Circuit Breaker (aiobreaker) → Retry (tenacity) → Semaphore → Timeout → Call

Usage:
    from modules.backend.core.resilience import ResilienceLogger, log_retry

    breaker = aiobreaker.CircuitBreaker(
        fail_max=5,
        timeout_duration=30,
        listeners=[ResilienceLogger("database")],
    )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=log_retry,
        reraise=True,
    )
    async def call_external():
        async with get_semaphore("external_api"):
            async with asyncio.timeout(7):
                return await client.get(url)
"""

from typing import Any

import aiobreaker

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class ResilienceLogger(aiobreaker.CircuitBreakerListener):
    """Circuit breaker listener that emits structured resilience events.

    Every state transition is logged with a standardized set of fields
    so that resilience events can be filtered and aggregated:

        jq 'select(.resilience_event != null)' logs/system.jsonl
    """

    def __init__(self, dependency: str) -> None:
        self.dependency = dependency

    def state_change(self, cb: aiobreaker.CircuitBreaker, old_state: Any, new_state: Any) -> None:
        event_map = {
            "open": "circuit_breaker_opened",
            "half-open": "circuit_breaker_half_open",
            "closed": "circuit_breaker_closed",
        }
        new_str = str(new_state).lower()
        event = event_map.get(new_str, f"circuit_breaker_{new_str}")
        log_level = "error" if new_str == "open" else "info"

        getattr(logger, log_level)(
            f"Circuit breaker {self.dependency}: {old_state} → {new_state}",
            extra={
                "resilience_event": event,
                "dependency": self.dependency,
                "failure_count": cb.fail_counter,
            },
        )

    def failure(self, cb: aiobreaker.CircuitBreaker, exception: Exception) -> None:
        logger.warning(
            f"Circuit breaker {self.dependency}: failure recorded",
            extra={
                "resilience_event": "circuit_breaker_failure",
                "dependency": self.dependency,
                "failure_count": cb.fail_counter,
                "error": str(exception),
            },
        )


def log_retry(retry_state: Any) -> None:
    """Tenacity before_sleep callback that emits structured retry events.

    Pass this as `before_sleep=log_retry` in any @retry decorator.

    Args:
        retry_state: tenacity.RetryCallState instance
    """
    duration_ms = None
    if retry_state.outcome_timestamp and retry_state.start_time:
        duration_ms = round(
            (retry_state.outcome_timestamp - retry_state.start_time) * 1000
        )

    error = None
    if retry_state.outcome and retry_state.outcome.failed:
        error = str(retry_state.outcome.exception())

    fn_name = getattr(retry_state.fn, "__name__", "unknown")

    logger.warning(
        f"Retrying {fn_name} (attempt {retry_state.attempt_number})",
        extra={
            "resilience_event": "retry_attempt",
            "dependency": fn_name,
            "attempt": retry_state.attempt_number,
            "duration_ms": duration_ms,
            "error": error,
        },
    )


def create_circuit_breaker(
    dependency: str,
    fail_max: int = 5,
    timeout_duration: int = 30,
) -> aiobreaker.CircuitBreaker:
    """Create a circuit breaker with structured logging.

    Args:
        dependency: Name of the external dependency (for logging)
        fail_max: Number of failures before opening
        timeout_duration: Seconds to wait before half-open test

    Returns:
        Configured CircuitBreaker instance
    """
    return aiobreaker.CircuitBreaker(
        fail_max=fail_max,
        timeout_duration=timeout_duration,
        listeners=[ResilienceLogger(dependency)],
    )
```

---

### Step 13: Update `main.py` Lifespan

**File:** `modules/backend/main.py`

Replace the existing `lifespan` function (lines 25-43) with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager — startup and graceful shutdown."""
    app_config = get_app_config()
    setup_logging(level=app_config.logging.level)

    if app_config.features.security_startup_checks_enabled:
        from modules.backend.gateway.security.startup_checks import run_startup_checks
        run_startup_checks()

    if app_config.features.observability_tracing_enabled:
        _init_tracing(app, app_config)

    if app_config.features.observability_metrics_enabled:
        _init_metrics(app)

    logger.info(
        "Application starting",
        extra={
            "app_name": app_config.application.name,
            "env": app_config.application.environment,
        },
    )
    yield

    logger.info("Application shutting down — draining pools")
    from modules.backend.core.concurrency import shutdown_pools
    await shutdown_pools()
    logger.info("Application shutdown complete")


def _init_tracing(app: FastAPI, app_config) -> None:
    """Initialize OpenTelemetry tracing if enabled and SDK is installed."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        tracing_config = app_config.observability.tracing

        resource = Resource.create({
            "service.name": tracing_config.service_name,
            "service.version": app_config.application.version,
            "deployment.environment": app_config.application.environment,
        })

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=tracing_config.otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)

        logger.info(
            "OpenTelemetry tracing initialized",
            extra={"endpoint": tracing_config.otlp_endpoint},
        )
    except ImportError:
        logger.warning("OpenTelemetry SDK not installed — tracing disabled")


def _init_metrics(app: FastAPI) -> None:
    """Initialize Prometheus metrics endpoint if enabled and library is installed."""
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics")
        logger.info("Prometheus metrics endpoint enabled at /metrics")
    except ImportError:
        logger.warning("prometheus-fastapi-instrumentator not installed — metrics disabled")
```

---

### Step 14: Update Health Checks

**File:** `modules/backend/api/health.py`

**14a.** Replace `asyncio.gather` in `readiness_check()` (lines 121-126) with `asyncio.TaskGroup`:

```python
@router.get("/health/ready")
async def readiness_check() -> dict[str, Any]:
    """
    Readiness check.

    Returns 200 if ready to serve traffic.
    Checks critical dependencies in parallel using TaskGroup.
    Returns 503 if any critical dependency is unhealthy.
    """
    from modules.backend.core.config import get_app_config
    timeout = get_app_config().observability.health_checks.ready_timeout_seconds

    db_result: dict[str, Any] = {"status": "error", "error": "check did not run"}
    redis_result: dict[str, Any] = {"status": "error", "error": "check did not run"}

    try:
        async with asyncio.timeout(timeout):
            async with asyncio.TaskGroup() as tg:
                db_task = tg.create_task(check_database())
                redis_task = tg.create_task(check_redis())
            db_result = db_task.result()
            redis_result = redis_task.result()
    except* Exception as eg:
        for exc in eg.exceptions:
            logger.warning("Health check task failed", extra={"error": str(exc)})

    checks = {
        "database": db_result,
        "redis": redis_result,
    }

    unhealthy_checks = [
        name for name, check in checks.items()
        if check.get("status") == "unhealthy"
    ]

    if unhealthy_checks:
        logger.warning(
            "Readiness check failed",
            extra={"unhealthy": unhealthy_checks, "checks": checks},
        )
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "checks": checks,
                "timestamp": utc_now().isoformat(),
            },
        )

    return {
        "status": "healthy",
        "checks": checks,
        "timestamp": utc_now().isoformat(),
    }
```

**14b.** Replace `asyncio.gather` in `detailed_health_check()` (lines 169-227) with `TaskGroup` and add pool status:

```python
@router.get("/health/detailed")
async def detailed_health_check() -> dict[str, Any]:
    """
    Detailed health check.

    Returns comprehensive status including dependency checks and pool metrics.
    Should be protected by authentication in production
    (controlled by observability.yaml health_checks.detailed_auth_required).
    """
    db_result: dict[str, Any] = {"status": "error", "error": "check did not run"}
    redis_result: dict[str, Any] = {"status": "error", "error": "check did not run"}

    try:
        async with asyncio.TaskGroup() as tg:
            db_task = tg.create_task(check_database())
            redis_task = tg.create_task(check_redis())
        db_result = db_task.result()
        redis_result = redis_task.result()
    except* Exception as eg:
        for exc in eg.exceptions:
            logger.warning("Detailed health check task failed", extra={"error": str(exc)})

    checks = {
        "database": db_result,
        "redis": redis_result,
    }

    try:
        from modules.backend.core.config import get_app_config
        app_config = get_app_config()
        app_settings = app_config.application

        app_info = {
            "name": app_settings.name,
            "env": app_settings.environment,
            "debug": app_settings.debug,
            "version": app_settings.version,
        }
    except Exception:
        app_info = {"status": "not_configured"}

    pools = _get_pool_status()

    statuses = [check.get("status") for check in checks.values()]
    if "unhealthy" in statuses or "error" in statuses:
        overall_status = "unhealthy"
    elif all(s == "not_configured" for s in statuses):
        overall_status = "healthy"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "application": app_info,
        "checks": checks,
        "pools": pools,
        "timestamp": utc_now().isoformat(),
    }


def _get_pool_status() -> dict[str, Any]:
    """Collect current pool and semaphore metrics for health reporting."""
    from modules.backend.core.concurrency import (
        _io_pool, _cpu_pool, _semaphores, _semaphore_capacities,
    )

    pools: dict[str, Any] = {}

    if _io_pool is not None:
        pools["thread_pool"] = {
            "max_workers": _io_pool._max_workers,
        }

    if _cpu_pool is not None:
        pools["process_pool"] = {
            "max_workers": _cpu_pool._max_workers,
        }

    if _semaphores:
        sem_status = {}
        for name, sem in _semaphores.items():
            sem_status[name] = {
                "capacity": _semaphore_capacities.get(name, "unknown"),
                "available": sem._value,
            }
        pools["semaphores"] = sem_status

    return pools
```

Note: The `_get_pool_status` function accesses internal attributes (`_max_workers`, `_value`) which are stable CPython internals used for observability only. This is acceptable per doc 08. Semaphore capacity is read from `_semaphore_capacities` (stored at creation time) because `asyncio.Semaphore` does not expose its initial value.

---

### Step 15: Create `events/__init__.py`

**File:** `modules/backend/events/__init__.py` (NEW)

```python
"""Event architecture — FastStream with Redis Streams."""
```

---

### Step 16: Create `events/broker.py`

**File:** `modules/backend/events/broker.py` (NEW, ~80 lines)

```python
"""
Event Broker.

FastStream RedisBroker setup with lazy initialization.
The broker connects to the same Redis instance used by Taskiq and caching.

Usage:
    from modules.backend.events.broker import get_event_broker

    broker = get_event_broker()
"""

from faststream import FastStream
from faststream.redis import RedisBroker

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_broker: RedisBroker | None = None
_app: FastStream | None = None


def create_event_broker() -> RedisBroker:
    """Create a new RedisBroker using the project's Redis URL.

    Returns:
        Configured RedisBroker instance
    """
    from modules.backend.core.config import get_redis_url

    redis_url = get_redis_url()
    broker = RedisBroker(redis_url)
    logger.info("Event broker created")
    return broker


def get_event_broker() -> RedisBroker:
    """Get the shared event broker (lazy initialization).

    Returns:
        Shared RedisBroker instance
    """
    global _broker
    if _broker is None:
        _broker = create_event_broker()
    return _broker


def create_event_app() -> FastStream:
    """Create a FastStream application for the event worker process.

    This is a factory function — FastStream CLI must be invoked with `--factory`:
        faststream run --factory modules.backend.events.broker:create_event_app

    Returns:
        FastStream app with broker and consumers registered
    """
    global _app
    if _app is not None:
        return _app

    broker = get_event_broker()

    from modules.backend.events.middleware import EventObservabilityMiddleware
    broker.middlewares = [EventObservabilityMiddleware]

    from modules.backend.events.consumers import notes as _notes_consumer  # noqa: F841

    _app = FastStream(broker)
    logger.info("Event worker application created")
    return _app
```

---

### Step 17: Create `events/schemas.py`

**File:** `modules/backend/events/schemas.py` (NEW, ~80 lines)

```python
"""
Event Schemas.

Standardized event envelope and domain-specific event types.
All events published through the event bus use the EventEnvelope base.

Naming convention for event_type: domain.entity.action (dot notation)
Stream naming convention: {domain}:{event-type} (colon-separated)

Usage:
    from modules.backend.events.schemas import NoteCreated

    event = NoteCreated(
        source="note-service",
        correlation_id=request_id,
        payload={"id": note.id, "title": note.title},
    )
"""

from uuid import uuid4

from pydantic import BaseModel, Field

from modules.backend.core.utils import utc_now


class EventEnvelope(BaseModel):
    """Base event envelope — all events inherit from this.

    Fields:
        event_id: Unique event identifier (auto-generated UUID)
        event_type: Domain event type in dot notation (e.g. notes.note.created)
        event_version: Schema version for forward compatibility
        timestamp: ISO 8601 UTC timestamp
        source: Service/module that published the event
        correlation_id: Request/session ID for tracing across services
        trace_id: OpenTelemetry trace ID (optional, populated when tracing is active)
        payload: Event-specific data
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    event_version: int = 1
    timestamp: str = Field(default_factory=lambda: utc_now().isoformat())
    source: str
    correlation_id: str
    trace_id: str | None = None
    payload: dict


class NoteCreated(EventEnvelope):
    """Published when a new note is created."""

    event_type: str = "notes.note.created"


class NoteUpdated(EventEnvelope):
    """Published when a note is updated."""

    event_type: str = "notes.note.updated"


class NoteArchived(EventEnvelope):
    """Published when a note is archived."""

    event_type: str = "notes.note.archived"
```

---

### Step 18: Create `events/middleware.py`

**File:** `modules/backend/events/middleware.py` (NEW, ~70 lines)

```python
"""
Event Observability Middleware.

Cross-cutting middleware applied to all event consumers.
Binds structlog context (correlation_id, event_type, source) for every
consumed event and measures processing duration.
"""

import time

import structlog
from faststream import BaseMiddleware

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class EventObservabilityMiddleware(BaseMiddleware):
    """Middleware that binds structlog context for event consumers.

    Applied to every message consumed from Redis Streams. Ensures that
    all log records within a consumer handler include the event's
    correlation_id and event_type for traceability.
    """

    async def on_consume(self, msg):
        # FastStream may deliver the message as a dict, a Pydantic model,
        # or a raw decoded value depending on the serializer. We extract
        # envelope fields defensively to ensure context is always bound.
        data: dict = {}
        if isinstance(msg, dict):
            data = msg
        elif hasattr(msg, "model_dump"):
            data = msg.model_dump()
        elif hasattr(msg, "__dict__"):
            data = vars(msg)

        structlog.contextvars.bind_contextvars(
            event_id=data.get("event_id", "unknown"),
            correlation_id=data.get("correlation_id", "unknown"),
            event_type=data.get("event_type", "unknown"),
            source="events",
        )
        self._start_time = time.monotonic()
        return await super().on_consume(msg)

    async def after_consume(self, err):
        duration_ms = round((time.monotonic() - self._start_time) * 1000, 1)

        if err:
            logger.error(
                "Event processing failed",
                extra={"duration_ms": duration_ms, "error": str(err)},
            )
        else:
            logger.info(
                "Event processed",
                extra={"duration_ms": duration_ms},
            )

        structlog.contextvars.unbind_contextvars(
            "event_id", "correlation_id", "event_type",
        )
        return await super().after_consume(err)
```

---

### Step 19: Create `events/publishers.py`

**File:** `modules/backend/events/publishers.py` (NEW, ~90 lines)

```python
"""
Event Publishers.

Domain-specific event publishers. Each publisher wraps the broker's
publish() method with the correct stream name and event schema.

Publishers check the events_publish_enabled feature flag before publishing.
When disabled, events are silently skipped (no error, no log noise).

Usage:
    from modules.backend.events.publishers import NoteEventPublisher

    publisher = NoteEventPublisher()
    await publisher.note_created(note, correlation_id=request_id)
"""

from modules.backend.core.logging import get_logger
from modules.backend.events.schemas import NoteArchived, NoteCreated, NoteUpdated

logger = get_logger(__name__)


def _get_trace_id() -> str | None:
    """Extract current OpenTelemetry trace ID if available."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            return format(span.get_span_context().trace_id, "032x")
    except ImportError:
        pass
    return None


class NoteEventPublisher:
    """Publishes note domain events to Redis Streams."""

    STREAM_CREATED = "notes:note-created"
    STREAM_UPDATED = "notes:note-updated"
    STREAM_ARCHIVED = "notes:note-archived"

    async def note_created(
        self, note_id: str, title: str, correlation_id: str,
    ) -> None:
        """Publish a notes.note.created event."""
        await self._publish(
            self.STREAM_CREATED,
            NoteCreated(
                source="note-service",
                correlation_id=correlation_id,
                trace_id=_get_trace_id(),
                payload={"note_id": note_id, "title": title},
            ),
        )

    async def note_updated(
        self, note_id: str, fields: list[str], correlation_id: str,
    ) -> None:
        """Publish a notes.note.updated event."""
        await self._publish(
            self.STREAM_UPDATED,
            NoteUpdated(
                source="note-service",
                correlation_id=correlation_id,
                trace_id=_get_trace_id(),
                payload={"note_id": note_id, "fields_updated": fields},
            ),
        )

    async def note_archived(
        self, note_id: str, correlation_id: str,
    ) -> None:
        """Publish a notes.note.archived event."""
        await self._publish(
            self.STREAM_ARCHIVED,
            NoteArchived(
                source="note-service",
                correlation_id=correlation_id,
                trace_id=_get_trace_id(),
                payload={"note_id": note_id},
            ),
        )

    async def _publish(self, stream: str, event) -> None:
        """Publish an event if the feature flag is enabled."""
        from modules.backend.core.config import get_app_config

        if not get_app_config().features.events_publish_enabled:
            return

        from modules.backend.events.broker import get_event_broker

        broker = get_event_broker()
        await broker.publish(event.model_dump(), channel=stream)
        logger.debug(
            "Event published",
            extra={"stream": stream, "event_type": event.event_type, "event_id": event.event_id},
        )
```

---

### Step 20: Create `events/consumers/notes.py`

**File:** `modules/backend/events/consumers/notes.py` (NEW, ~140 lines)

```python
"""
Note Event Consumer.

Subscribes to note domain events and processes them with the full
resilience stack: circuit breaker → retry → timeout.
Failed events are routed to a dead letter queue (DLQ) after retries
are exhausted.

This is a reference implementation showing the consumer pattern.
In a real application, the handler would trigger downstream actions
(search indexing, notifications, analytics, etc.).

Run with: python cli.py --service event-worker
"""

import asyncio

import aiobreaker
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from modules.backend.core.logging import get_logger
from modules.backend.core.resilience import ResilienceLogger, log_retry
from modules.backend.events.broker import get_event_broker
from modules.backend.events.schemas import EventEnvelope

logger = get_logger(__name__)

broker = get_event_broker()

_note_consumer_breaker = aiobreaker.CircuitBreaker(
    fail_max=5,
    timeout_duration=30,
    listeners=[ResilienceLogger("note-consumer")],
)


async def _send_to_dlq(stream: str, event: EventEnvelope, error: Exception) -> None:
    """Publish a failed event to the dead letter queue stream.

    DLQ stream name follows the convention: dlq:{original_stream}
    The original event is preserved with added error metadata.
    """
    from modules.backend.core.config import get_app_config

    dlq_config = get_app_config().events.dlq
    if not dlq_config.enabled:
        return

    dlq_stream = f"{dlq_config.stream_prefix}:{stream}"
    dlq_payload = event.model_dump()
    dlq_payload["_dlq_error"] = str(error)
    dlq_payload["_dlq_original_stream"] = stream

    try:
        await broker.publish(dlq_payload, channel=dlq_stream)
        logger.warning(
            "Event sent to DLQ",
            extra={
                "dlq_stream": dlq_stream,
                "event_id": event.event_id,
                "error": str(error),
            },
        )
    except Exception as dlq_err:
        logger.error(
            "Failed to send event to DLQ",
            extra={
                "dlq_stream": dlq_stream,
                "event_id": event.event_id,
                "dlq_error": str(dlq_err),
                "original_error": str(error),
            },
        )


async def _handle_event(stream: str, event: EventEnvelope) -> None:
    """Process an event with resilience, routing failures to the DLQ."""
    try:
        await _process_note_event_with_resilience(event)
    except Exception as exc:
        logger.error(
            "Event processing failed after retries",
            extra={
                "event_type": event.event_type,
                "event_id": event.event_id,
                "error": str(exc),
            },
        )
        await _send_to_dlq(stream, event, exc)


@broker.subscriber("notes:note-created", group="note-processor")
async def handle_note_created(data: dict) -> None:
    """Process a notes.note.created event.

    Demonstrates the consumer pattern with:
    - Event envelope parsing
    - Resilience stack (circuit breaker + retry + timeout)
    - DLQ routing on terminal failure
    - Structured logging with correlation context
    """
    event = EventEnvelope(**data)

    logger.info(
        "Processing note created event",
        extra={
            "note_id": event.payload.get("note_id"),
            "title": event.payload.get("title"),
            "correlation_id": event.correlation_id,
        },
    )

    await _handle_event("notes:note-created", event)


@broker.subscriber("notes:note-updated", group="note-processor")
async def handle_note_updated(data: dict) -> None:
    """Process a notes.note.updated event."""
    event = EventEnvelope(**data)

    logger.info(
        "Processing note updated event",
        extra={
            "note_id": event.payload.get("note_id"),
            "fields": event.payload.get("fields_updated"),
            "correlation_id": event.correlation_id,
        },
    )

    await _handle_event("notes:note-updated", event)


@broker.subscriber("notes:note-archived", group="note-processor")
async def handle_note_archived(data: dict) -> None:
    """Process a notes.note.archived event."""
    event = EventEnvelope(**data)

    logger.info(
        "Processing note archived event",
        extra={
            "note_id": event.payload.get("note_id"),
            "correlation_id": event.correlation_id,
        },
    )

    await _handle_event("notes:note-archived", event)


@_note_consumer_breaker
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    before_sleep=log_retry,
    reraise=True,
)
async def _process_note_event_with_resilience(event: EventEnvelope) -> None:
    """Process event with the full resilience stack.

    In a real application, this would call downstream services
    (search indexing, notification dispatch, analytics pipeline).
    The circuit breaker + retry + timeout pattern protects against
    downstream failures. If this raises after all retries, the caller
    routes the event to the DLQ.
    """
    async with asyncio.timeout(30):
        logger.info(
            "Note event processed successfully",
            extra={
                "event_type": event.event_type,
                "event_id": event.event_id,
            },
        )
```

---

### Step 21: Create `events/consumers/__init__.py`

**File:** `modules/backend/events/consumers/__init__.py` (NEW)

```python
"""Event consumers — subscribe to domain events from Redis Streams."""
```

---

### Step 22: Wire `NoteEventPublisher` into `NoteService`

**File:** `modules/backend/services/note.py`

**22a.** Add import for the publisher. Add after line 4 (after the existing imports):

```python
from modules.backend.events.publishers import NoteEventPublisher
```

**22b.** Add the publisher to `__init__`. Replace the current `__init__` (lines 24-26):

```python
def __init__(self, session: AsyncSession) -> None:
    super().__init__(session)
    self.repo = NoteRepository(session)
```

With:

```python
def __init__(self, session: AsyncSession) -> None:
    super().__init__(session)
    self.repo = NoteRepository(session)
    self._event_publisher = NoteEventPublisher()
```

**Known caveat:** Events are published after the repository call but before the session transaction commits externally. If the transaction later fails, the event has already been published — this is an at-most-once delivery concern. The transactional outbox pattern (out of scope for this skeleton) would address this by writing events to a DB outbox table within the same transaction. For the skeleton, this trade-off is acceptable and documented here for future reference.

**22c.** Publish event after note creation. In `create_note()`, after line 48 (`self._log_debug("Note created", note_id=note.id)`), add:

```python
        await self._event_publisher.note_created(
            note_id=str(note.id),
            title=data.title,
            correlation_id=self._get_correlation_id(),
        )
```

**22d.** Publish event after note update. In `update_note()`, after line 145 (`return note`), add before the return:

```python
        await self._event_publisher.note_updated(
            note_id=str(note.id),
            fields=list(update_data.keys()),
            correlation_id=self._get_correlation_id(),
        )
```

**22e.** Publish event after note archive. In `archive_note()`, replace lines 177-178:

```python
self._log_operation("Archiving note", note_id=note_id)
return await self.repo.archive(note_id)
```

With:

```python
self._log_operation("Archiving note", note_id=note_id)
note = await self.repo.archive(note_id)
await self._event_publisher.note_archived(
    note_id=str(note.id),
    correlation_id=self._get_correlation_id(),
)
return note
```

**22f.** Add the `_get_correlation_id` helper method to `NoteService`. Add it as the last method in the class:

```python
@staticmethod
def _get_correlation_id() -> str:
    """Extract request_id from structlog context as correlation_id.

    Falls back to a new UUID if not in a request context.
    """
    import uuid

    import structlog

    ctx = structlog.contextvars.get_contextvars()
    return ctx.get("request_id", str(uuid.uuid4()))
```

---

### Step 23: Add `--service event-worker` to CLI

**File:** `cli.py`

**23a.** Add `"event-worker"` to the `--service` choices. On line 79, the current choices are:

```python
type=click.Choice(["server", "worker", "scheduler", "health", "config", "test", "info", "migrate", "telegram-poll"]),
```

Replace with:

```python
type=click.Choice(["server", "worker", "scheduler", "health", "config", "test", "info", "migrate", "telegram-poll", "event-worker"]),
```

**23b.** Add `"event-worker"` to `LONG_RUNNING_SERVICES` (line 32):

```python
LONG_RUNNING_SERVICES = {"server", "worker", "scheduler", "telegram-poll", "event-worker"}
```

**23c.** Add the dispatch case in the `main()` function. After line 239 (`run_telegram_poll(logger)`), add:

```python
    elif service == "event-worker":
        run_event_worker(logger, workers)
```

**23d.** Add the `run_event_worker` function. Insert it after the `run_telegram_poll` function (after line 421):

```python
def run_event_worker(logger, workers: int) -> None:
    """Start the FastStream event consumer worker."""
    from modules.backend.core.config import get_app_config

    features = get_app_config().features
    if not features.events_enabled:
        click.echo(
            click.style(
                "Error: events_enabled is false in features.yaml. "
                "Enable it to run the event worker.",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    logger.info("Starting event worker", extra={"workers": workers})

    cmd = [
        sys.executable, "-m", "faststream",
        "run",
        "--factory",
        "modules.backend.events.broker:create_event_app",
        "--workers", str(workers),
    ]

    click.echo(f"Starting event worker with {workers} worker(s)")
    click.echo("Press Ctrl+C to stop\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Event worker stopped")
    except subprocess.CalledProcessError as e:
        logger.error("Event worker failed to start", extra={"exit_code": e.returncode})
        sys.exit(e.returncode)
```

**23e.** Update the `show_info` function's service list (around line 671). Add after the telegram-poll line:

```python
click.echo("  event-worker   Event consumer worker (FastStream)")
```

And add to the examples section:

```python
click.echo("  python cli.py --service event-worker --verbose")
```

**23f.** Update the CLI docstring (lines 8-15) to include event-worker:

```
Usage:
    python cli.py --help
    python cli.py --service server --verbose
    python cli.py --service server --action stop
    python cli.py --service health --debug
    python cli.py --service config
    python cli.py --service test --test-type unit
    python cli.py --service event-worker --verbose
```

---

### Step 24: Unit Tests for `core/concurrency.py`

**File:** `tests/unit/backend/core/test_concurrency.py` (NEW, ~150 lines)

Tests to write:

1. `test_traced_thread_pool_propagates_contextvars` — Set a contextvar, submit work to `TracedThreadPoolExecutor`, verify the contextvar is accessible in the worker thread.
2. `test_traced_thread_pool_propagates_structlog_context` — Bind structlog context, submit work, verify context is present in the worker thread.
3. `test_get_io_pool_creates_pool_lazily` — Call `get_io_pool()` twice, verify same instance returned.
4. `test_get_cpu_pool_creates_pool_lazily` — Call `get_cpu_pool()` twice, verify same instance returned.
5. `test_get_semaphore_creates_with_config_capacity` — Mock config with `semaphores.database=50`, call `get_semaphore("database")`, verify `._value == 50`.
6. `test_get_semaphore_returns_same_instance` — Call `get_semaphore("database")` twice, verify same instance.
7. `test_shutdown_pools_cleans_up` — Create pools, call `shutdown_pools()`, verify globals are `None` and semaphores dict is empty.
8. `test_traced_thread_pool_executes_function` — Submit a simple function, verify result.

Each test should clean up global state in a fixture to avoid cross-test contamination.

---

### Step 25: Unit Tests for `core/resilience.py`

**File:** `tests/unit/backend/core/test_resilience.py` (NEW, ~150 lines)

Tests to write:

1. `test_resilience_logger_state_change_open` — Create `ResilienceLogger("db")`, call `state_change()` with new state "open", verify structured log emitted at error level with `resilience_event="circuit_breaker_opened"`.
2. `test_resilience_logger_state_change_closed` — Same but state "closed", verify info level.
3. `test_resilience_logger_state_change_half_open` — Same but state "half-open".
4. `test_resilience_logger_failure` — Call `failure()`, verify warning log with `resilience_event="circuit_breaker_failure"`.
5. `test_log_retry_emits_structured_event` — Create a mock `retry_state` with `attempt_number=2`, `fn.__name__="call_api"`, verify log emitted with `resilience_event="retry_attempt"`.
6. `test_log_retry_handles_no_outcome` — `retry_state` with `outcome=None`, verify no crash.
7. `test_create_circuit_breaker_returns_configured_breaker` — Call `create_circuit_breaker("redis", fail_max=3, timeout_duration=15)`, verify returned breaker has correct config and `ResilienceLogger` attached.
8. `test_create_circuit_breaker_default_values` — Call with just dependency name, verify defaults (5, 30).

---

### Step 26: Unit Tests for Event Schemas and Publisher

**File:** `tests/unit/backend/events/test_events.py` (NEW, ~180 lines)

Test files to create first: `tests/unit/backend/events/__init__.py` (empty).

Tests to write:

1. `test_event_envelope_auto_generates_fields` — Create `EventEnvelope(event_type="test", source="unit", correlation_id="abc", payload={})`, verify `event_id` is a UUID string, `timestamp` is ISO format, `event_version` is 1.
2. `test_event_envelope_custom_fields` — Override `event_id`, `timestamp`, `trace_id`, verify they are preserved.
3. `test_note_created_has_correct_event_type` — `NoteCreated(...)` has `event_type == "notes.note.created"`.
4. `test_note_updated_has_correct_event_type` — Same for updated.
5. `test_note_archived_has_correct_event_type` — Same for archived.
6. `test_event_envelope_serializes_to_dict` — Call `.model_dump()`, verify all fields present.
7. `test_note_event_publisher_skips_when_disabled` — Mock `get_app_config().features.events_publish_enabled = False`, call `note_created()`, verify broker.publish is NOT called.
8. `test_note_event_publisher_publishes_when_enabled` — Mock `events_publish_enabled = True`, mock broker, call `note_created()`, verify `broker.publish` called with correct stream and payload.
9. `test_note_event_publisher_created_stream_name` — Verify `NoteEventPublisher.STREAM_CREATED == "notes:note-created"`.
10. `test_note_event_publisher_updated_stream_name` — Verify updated stream name.
11. `test_note_event_publisher_archived_stream_name` — Verify archived stream name.

---

### Step 27: Unit Tests for Event Consumer

**File:** `tests/unit/backend/events/test_consumers.py` (NEW, ~160 lines)

Tests to write:

1. `test_handle_note_created_processes_event` — Call `handle_note_created()` directly with a valid event dict, verify it completes without error.
2. `test_handle_note_updated_processes_event` — Same for updated.
3. `test_handle_note_archived_processes_event` — Same for archived.
4. `test_process_with_resilience_succeeds` — Call `_process_note_event_with_resilience()` with a valid event, verify success.
5. `test_consumer_logs_correlation_id` — Verify that the handler logs include `correlation_id` from the event.
6. `test_consumer_handles_invalid_event_gracefully` — Pass malformed dict, verify appropriate error handling.
7. `test_send_to_dlq_publishes_on_failure` — Mock `_process_note_event_with_resilience` to raise, verify `broker.publish` is called with the DLQ stream name (`dlq:notes:note-created`) and the event payload includes `_dlq_error`.
8. `test_send_to_dlq_skips_when_disabled` — Mock `get_app_config().events.dlq.enabled = False`, verify `broker.publish` is NOT called after a processing failure.
9. `test_send_to_dlq_logs_error_on_publish_failure` — Mock DLQ publish to raise, verify error is logged but does not propagate (consumer does not crash).

All consumer tests call handlers directly (no Redis needed). This is the black box testing pattern — test the handler's interface, not the broker wiring.

---

### Step 28: Integration Tests for Enhanced Health Endpoint

**File:** `tests/integration/backend/api/test_health_enhanced.py` (NEW, ~100 lines)

Tests to write:

1. `test_readiness_returns_healthy_with_task_group` — GET `/health/ready`, verify 200 and `status=healthy`.
2. `test_detailed_includes_pools_key` — GET `/health/detailed`, verify response includes `pools` key.
3. `test_detailed_returns_app_info` — Verify `application` section has `name`, `env`, `version`.
4. `test_readiness_timeout_from_config` — Verify the timeout is sourced from `observability.yaml`.

Uses the existing `client` fixture from `tests/integration/conftest.py`. The mock config fixtures must be updated to include `observability`, `concurrency`, and `events` sections.

**Important:** Update `tests/integration/conftest.py` — the `_create_mock_app_config()` function must return an object that also has `.observability`, `.concurrency`, and `.events` properties. Add minimal mock data for these three configs.

Similarly, update `tests/unit/conftest.py` — the `mock_app_config` fixture must include the new properties.

---

### Step 29: Run Full Test Suite

```bash
pytest tests/ -v --tb=short
```

All existing tests must pass. Target: zero regressions plus all new tests passing.

**Expected test count:** ~382 existing + ~43 new = ~425 tests.

If any existing tests fail due to the config changes (e.g., `AppConfig.__init__` now loads three additional YAML files), the conftest mock fixtures need updating (see Step 28 note).

---

### Step 30: Update `AGENTS.md`

**File:** `AGENTS.md`

Add the following to the **Key Modules** table:

```
| `modules/backend/core/concurrency.py` | Thread/process pools, semaphores, TracedThreadPoolExecutor |
| `modules/backend/core/resilience.py` | Circuit breaker listener, retry callback, resilience patterns |
| `modules/backend/events/` | Event bus (FastStream + Redis Streams) |
```

Add to the **Configuration** section:

```
- Observability settings: `config/settings/observability.yaml` via `get_app_config().observability`
- Concurrency settings: `config/settings/concurrency.yaml` via `get_app_config().concurrency`
- Event settings: `config/settings/events.yaml` via `get_app_config().events`
```

Add to the **Entry Points** section:

```
- `python cli.py --service event-worker` — FastStream event consumer
```

---

### Step 31: Merge Branch Back to Main

Only after all tests pass:

```bash
git add -A && git commit -m "feat: add concurrency, events, and observability infrastructure"
git checkout main
git merge feat/concurrency-events-observability
git branch -d feat/concurrency-events-observability
```

---

## New Files Summary

| File | Purpose | Lines (est.) |
|------|---------|------|
| `config/settings/observability.yaml` | Tracing, metrics, health check config | 25 |
| `config/settings/concurrency.yaml` | Pool sizes, semaphores, shutdown timing | 40 |
| `config/settings/events.yaml` | Broker, streams, consumer config | 50 |
| `modules/backend/core/concurrency.py` | Pools, semaphores, `TracedThreadPoolExecutor` | 120 |
| `modules/backend/core/resilience.py` | `ResilienceLogger`, retry callback, breaker factory | 150 |
| `modules/backend/events/__init__.py` | Package marker | 2 |
| `modules/backend/events/broker.py` | FastStream RedisBroker setup | 80 |
| `modules/backend/events/schemas.py` | `EventEnvelope` + note domain events | 80 |
| `modules/backend/events/middleware.py` | `EventObservabilityMiddleware` | 70 |
| `modules/backend/events/publishers.py` | `NoteEventPublisher` | 90 |
| `modules/backend/events/consumers/__init__.py` | Package marker | 2 |
| `modules/backend/events/consumers/notes.py` | Note event consumer with resilience + DLQ | 170 |
| `tests/unit/backend/core/test_concurrency.py` | Concurrency module tests | 150 |
| `tests/unit/backend/core/test_resilience.py` | Resilience module tests | 150 |
| `tests/unit/backend/events/__init__.py` | Package marker | 0 |
| `tests/unit/backend/events/test_events.py` | Event schema + publisher tests | 180 |
| `tests/unit/backend/events/test_consumers.py` | Consumer handler + DLQ tests | 160 |
| `tests/integration/backend/api/test_health_enhanced.py` | Enhanced health endpoint tests | 100 |

## Modified Files Summary

| File | Change |
|------|--------|
| `requirements.txt` | Add uvloop, tenacity, faststream[redis], OTel, Prometheus; move aiobreaker |
| `modules/backend/core/config_schema.py` | Add `ObservabilitySchema`, `ConcurrencySchema`, `EventsSchema` + sub-schemas |
| `modules/backend/core/config.py` | Import 3 new schemas, load 3 new YAMLs in AppConfig, add 3 properties |
| `config/settings/features.yaml` | Add `events_enabled`, `events_publish_enabled`, `observability_tracing_enabled`, `observability_metrics_enabled` |
| `modules/backend/core/logging.py` | Add `events`/`agent`/`unknown` to VALID_SOURCES, add `add_trace_context` processor |
| `modules/backend/core/middleware.py` | Default source `"unknown"` instead of `None` |
| `modules/backend/main.py` | Lifespan with pool cleanup, `_init_tracing`, `_init_metrics` |
| `modules/backend/api/health.py` | `TaskGroup` instead of `gather`, add pool status, `_get_pool_status` |
| `modules/backend/services/note.py` | Publish events after create/update/archive |
| `cli.py` | Add `--service event-worker`, `run_event_worker()` function |
| `AGENTS.md` | Document new modules |
| `tests/unit/conftest.py` | Add mock properties for observability, concurrency, events configs |
| `tests/integration/conftest.py` | Add mock properties for observability, concurrency, events configs |

---

## Rules Compliance

| Rule | Status |
|------|--------|
| No hardcoded values | All config in YAML; pool sizes, timeouts, stream names from config |
| Absolute imports only | All imports use `from modules.backend.core...` |
| Centralized logging | Uses `get_logger(__name__)` everywhere |
| `.project_root` for root | Existing pattern unchanged |
| `--verbose`/`--debug` on scripts | Event worker uses existing CLI flags |
| Centralized `.env` for secrets | No new secrets — uses existing `REDIS_PASSWORD` |
| No hardcoded fallbacks | Missing config = startup failure |
| No helper/wrapper scripts | All code in `modules/` or `core/` |
| Files under 500 lines (doc 07) | All new files under 200 lines |
| Minimal `__init__.py` | All `__init__.py` are 1-2 line package markers |
| Fail fast (P5) | Missing YAML config raises at `AppConfig.__init__` |
| Secure by default (P8) | Events disabled by default, tracing disabled, metrics disabled |
| No layer skipping | Events published from service layer, not API layer |

---

## Usage After Implementation

```bash
# Start the server (existing)
python cli.py --service server --verbose

# Start the event worker (new)
python cli.py --service event-worker --verbose

# Create a note (triggers event if events_publish_enabled=true)
curl -X POST http://localhost:8000/api/v1/notes \
  -H "Content-Type: application/json" \
  -H "X-Frontend-ID: api" \
  -d '{"title": "Test Note", "content": "Hello events"}'

# The event worker logs will show:
#   Event processed | event_type=notes.note.created | correlation_id=<request_id>

# Check health (now includes pool status)
curl http://localhost:8000/health/detailed | python -m json.tool

# Filter resilience events in logs
jq 'select(.resilience_event != null)' logs/system.jsonl
```

---

## Future Enhancements (Out of Scope)

1. **Telemetry debug API** — `POST /api/telemetry/debug` with Redis-backed tokens (requires auth system)
2. **Transactional outbox** — atomic DB-write + event-publish for critical events
3. **DLQ replay CLI** — `python cli.py --service event-worker --replay-dlq`
4. **Prometheus custom metrics** — circuit breaker state gauges, consumer lag gauges
5. **Consumer lag monitoring** — scheduled Taskiq task running `XINFO GROUPS`
6. **Stale message recovery** — scheduled `XAUTOCLAIM` task per consumer group
7. **Event-session architecture** (doc 35) — session-as-primitive, streaming coordinator
8. **`InterpreterPoolExecutor`** — evaluate when Python 3.14 is the deployment standard
9. **OTel auto-instrumentation** — httpx, SQLAlchemy, Redis instrumentation
10. **Backpressure / skip-to-latest** — staleness check for time-sensitive event streams
