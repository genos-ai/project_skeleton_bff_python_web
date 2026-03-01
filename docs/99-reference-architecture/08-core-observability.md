# 08 — Observability

*Version: 3.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 3.0.0 (2026-03-01): Added three-pillar observability (logs, metrics, traces). Added OpenTelemetry distributed tracing as core standard. Added context propagation across async/thread/process boundaries. Added profiling tools (py-spy, yappi, Scalene, asyncio pstree). Added resilience event logging contract. Added circuit breaker and concurrency metrics. Added multi-process Prometheus guidance. Promoted Telemetry Debug API from future enhancement to standard. Integrated with 16-core-concurrency-and-resilience.md.
- 2.0.0 (2026-02-11): Added frontend tracking (X-Frontend-ID), improved health checks, clarified production deployment
- 1.0.0 (2025-01-27): Initial generic observability standard

---

## Context

When something breaks in production, the first question is always "what happened?" If the answer requires SSHing into a server and grepping unstructured log files, debugging takes hours instead of minutes. This document ensures that every application produces structured, queryable, correlated observability signals from day one — so that tracing a request from client to database to response is a single query, not an investigation.

The core design is built around the `X-Request-ID` header: every request gets a unique identifier that propagates through all log entries, downstream calls, and the response. Combined with `X-Frontend-ID` (which identifies whether the request came from web, CLI, mobile, or Telegram), any production issue can be traced to its source and followed through the entire system. This is implemented in the skeleton code itself, not deferred to production infrastructure.

Version 3.0.0 adds the two missing pillars: **distributed traces** (via OpenTelemetry) and **profiling** (via py-spy, yappi, and asyncio introspection). With the introduction of concurrency patterns in **16-core-concurrency-and-resilience.md** — thread pools, process pools, circuit breakers, retry logic — observability must follow work across every boundary. A `request_id` that disappears when you call `asyncio.to_thread()` or `ProcessPoolExecutor.submit()` means you cannot trace a request through your system. A circuit breaker that trips silently means you don't know why requests are failing. A coroutine that's stuck on an `await` looks healthy to a CPU profiler. This version closes those gaps.

The document separates skeleton features (structured logging, request context, health checks, context propagation) from production deployment (Prometheus, Loki, Grafana/Tempo, OpenTelemetry Collector). The skeleton ships with everything needed to produce good signals; the production stack is infrastructure that consumes them.

---

## Overview

This document defines observability standards for the skeleton and applications built from it.

**Core Skeleton Features** (implemented in code):
- Structured logging with structlog
- Request context middleware (X-Request-ID, X-Frontend-ID)
- Context propagation across async, thread, and process boundaries
- Health check endpoints with dependency and circuit breaker status
- Response timing headers
- Telemetry debug API for per-session verbose logging
- Resilience event logging (circuit breakers, retries, timeouts)

**Production Deployment** (infrastructure, not in skeleton code):
- OpenTelemetry for distributed tracing
- Prometheus for metrics collection
- Loki for log aggregation
- Grafana for dashboards and alerting
- Tempo or Jaeger for trace storage and visualization

**Development and Debugging:**
- py-spy for production thread/process debugging
- yappi for deterministic async profiling
- Scalene for memory and CPU line-level profiling
- `python -m asyncio pstree` for live async task inspection (3.14+)

---

## The Three Pillars

Observability is not logging. Logging is one of three pillars. All three are required for production systems.

| Pillar | Tool | Answers | Skeleton? |
|--------|------|---------|-----------|
| **Logs** | structlog → Loki | What happened? (narrative events with context) | Yes |
| **Metrics** | Prometheus | How much? How fast? How often? (aggregates) | Hooks only |
| **Traces** | OpenTelemetry → Tempo/Jaeger | Where did time go? (request flow across boundaries) | Hooks only |

**Logs** tell you a circuit breaker tripped. **Metrics** tell you it's been tripping 40 times per minute. **Traces** show you the exact call chain from the user's request through the async task group, into the thread pool, to the external API call that timed out.

You need all three. Any two without the third leaves blind spots that will cost you hours during an incident.

---

## Request Context

### Standard Headers

| Header | Direction | Purpose |
|--------|-----------|---------|
| `X-Request-ID` | In/Out | Unique request identifier for tracing |
| `X-Frontend-ID` | In | Source frontend identifier |
| `X-Response-Time` | Out | Response duration in milliseconds |
| `X-Debug-Token` | In | Per-session debug mode activation (see Telemetry Debug API) |
| `traceparent` | In/Out | W3C Trace Context propagation (when OTel enabled) |

### X-Request-ID

Every request receives a unique identifier:
- Generated by middleware if not provided
- Propagated to all downstream calls
- Included in all log entries
- Returned in response headers
- **Mapped to OpenTelemetry `trace_id` when tracing is enabled** (see Distributed Tracing section)

```python
# Accessing in endpoint
request_id = request.state.request_id
```

### X-Frontend-ID

Identifies the source frontend for debugging and analytics:

| Value | Description |
|-------|-------------|
| `web` | Web browser frontend |
| `cli` | Command-line interface |
| `tui` | Terminal user interface (Textual) |
| `mobile` | Mobile application |
| `telegram` | Telegram bot |
| `api` | Direct API integration |
| `agent` | Autonomous agent (agentic architecture) |
| `internal` | Internal service calls |
| `unknown` | Not provided or unrecognized |

```python
# Accessing in endpoint
frontend = request.state.frontend
```

**Implementation**: Frontends should send this header with every request. The middleware validates against known values and defaults to "unknown" if not recognized.

### Response Timing

The `X-Response-Time` header returns the server-side processing time in milliseconds. This helps identify slow requests without requiring server log access.

---

## Logging

### Standard: structlog

All Python applications use structlog for structured logging.

Rationale:
- Structured JSON output for parsing
- Context binding across request via `contextvars`
- Compatible with standard logging
- Easy to query and analyze
- **contextvars-based context is safe for asyncio and threading** (see Context Propagation)

### Log Format

Production logs output as JSON with these fields:
- `timestamp`: ISO8601 UTC
- `level`: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `logger`: Module/component name
- `message`: Human-readable message
- `request_id`: Correlation ID for request tracing
- `frontend`: Source frontend identifier
- `trace_id`: OpenTelemetry trace ID (when tracing enabled)
- `span_id`: OpenTelemetry span ID (when tracing enabled)
- Additional context fields as needed

Development logs may use human-readable format for convenience.

### Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | Detailed diagnostic information for troubleshooting |
| INFO | Normal operation events worth recording |
| WARNING | Unexpected conditions that don't prevent operation |
| ERROR | Failures that affect single operation |
| CRITICAL | Failures that affect system availability |

### What to Log

**Always log:**
- Application startup and shutdown
- Configuration loaded (without secrets)
- External service calls (endpoint, duration, status)
- Database query performance (slow queries)
- Authentication events
- Error conditions with context
- **Resilience events** (circuit breaker state changes, retry attempts, timeouts — see Resilience Event Logging)
- **Concurrency events** (executor pool exhaustion, semaphore contention — see Concurrency Metrics)

**Never log:**
- Passwords or tokens
- Full credit card numbers
- Personal data beyond identifiers
- Request/response bodies with sensitive data

### Log Storage

All logs are written to a single JSONL file: `logs/system.jsonl`. Filter by the `source` field to isolate logs from a specific origin.

#### Structured Fields

Every JSON log record contains:

| Field | Description | Presence |
|-------|-------------|----------|
| `timestamp` | ISO 8601 UTC timestamp | Always |
| `level` | Log level (debug, info, warning, error, critical) | Always |
| `logger` | Module path (e.g., `modules.backend.api.health`) | Always |
| `event` | Log message | Always |
| `func_name` | Function that emitted the log | Always |
| `lineno` | Line number in source file | Always |
| `source` | Origin context (web, cli, tui, telegram, api, agent, tasks, internal) | When set explicitly |
| `request_id` | Request correlation ID | In HTTP request context |
| `trace_id` | OpenTelemetry trace ID | When tracing enabled |
| `span_id` | OpenTelemetry span ID | When tracing enabled |

Additional fields are added by callers via extra kwargs or structlog context binding.

#### Source Values

Source is always set explicitly — never guessed from logger names.

| Source | Set by |
|--------|--------|
| `web` | Middleware, from `X-Frontend-ID: web` header |
| `cli` | Entry point binding in `cli.py`, `chat.py` |
| `tui` | Entry point binding in `tui.py` |
| `mobile` | Middleware, from `X-Frontend-ID: mobile` header |
| `telegram` | `log_with_source()` in telegram handlers |
| `agent` | `log_with_source()` in agentic task handlers |
| `api` | Middleware, from `X-Frontend-ID: api` header |
| `tasks` | `log_with_source()` in background tasks |
| `internal` | `log_with_source()` in internal services |

#### File Rotation

- **Max size**: 10MB per file (configurable in `logging.yaml`)
- **Backups**: 5 rotated files kept (`system.jsonl.1`, `system.jsonl.2`, etc.)
- **Encoding**: UTF-8

#### Troubleshooting with Log Files

```bash
# View recent errors
jq 'select(.level == "error")' logs/system.jsonl | tail -20

# Find all logs for a specific request
jq 'select(.request_id == "abc-123")' logs/system.jsonl

# Filter by source
jq 'select(.source == "telegram")' logs/system.jsonl

# Find all resilience events (circuit breakers, retries, timeouts)
jq 'select(.resilience_event != null)' logs/system.jsonl

# Correlate logs with a specific trace
jq 'select(.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736")' logs/system.jsonl

# Watch logs in real-time
tail -f logs/system.jsonl | jq .

# Count errors by source
jq 'select(.level == "error") | .source' logs/system.jsonl | sort | uniq -c | sort -rn
```

#### Explicit Source Logging

For non-HTTP contexts (no middleware), set source explicitly:

```python
from modules.backend.core.logging import get_logger, log_with_source

logger = get_logger(__name__)

# In HTTP context: source is set automatically by middleware from X-Frontend-ID header
logger.info("User logged in", extra={"user_id": 123})

# Outside HTTP context: set source explicitly
log_with_source(logger, "tasks", "warning", "Slow query", query_ms=150)
```

### Centralized Logging (Production)

For production deployments, aggregate logs using Loki:

```yaml
# Example Loki configuration
# loki:
#   url: http://loki:3100/loki/api/v1/push
#   labels:
#     app: ${APP_NAME}
#     env: ${APP_ENV}
```

Use Promtail or similar agent to ship logs from `logs/` to Loki.

---

## Resilience Event Logging

All resilience events — circuit breaker state changes, retry attempts, timeout breaches — must be logged with a standard structure. This enables dashboards that show system health at a glance and alerting that catches degradation before it becomes an outage.

### Logging Contract

Every resilience event includes these fields:

| Field | Type | Description |
|-------|------|-------------|
| `resilience_event` | string | Event type (see table below) |
| `dependency` | string | Name of the external dependency |
| `duration_ms` | float | Time elapsed for the operation |
| `attempt` | int | Retry attempt number (1-based), null for non-retry events |
| `error` | string | Error message (for failures) |

### Event Types

| `resilience_event` | When Emitted | Level |
|---------------------|-------------|-------|
| `circuit_breaker_opened` | Failure count exceeded threshold | ERROR |
| `circuit_breaker_half_open` | Testing recovery after timeout | WARNING |
| `circuit_breaker_closed` | Recovery confirmed | INFO |
| `circuit_breaker_rejected` | Call rejected by open breaker | WARNING |
| `retry_attempt` | About to retry after failure | WARNING |
| `retry_exhausted` | All retry attempts failed | ERROR |
| `timeout_exceeded` | Operation exceeded timeout | WARNING |
| `bulkhead_rejected` | Semaphore full, call rejected | WARNING |
| `bulkhead_contention` | Semaphore wait exceeded 1 second | WARNING |

### Implementation

```python
import structlog

logger = structlog.get_logger()

# Circuit breaker state change
logger.error(
    "Circuit breaker opened — stopping calls to market data API",
    resilience_event="circuit_breaker_opened",
    dependency="market_data_api",
    failure_count=5,
    threshold=5,
)

# Retry attempt
logger.warning(
    "Retrying broker API call",
    resilience_event="retry_attempt",
    dependency="broker_api",
    attempt=2,
    max_attempts=3,
    error="ConnectionError: connection reset",
    duration_ms=1523.4,
)

# Timeout
logger.warning(
    "Market data fetch exceeded timeout",
    resilience_event="timeout_exceeded",
    dependency="market_data_api",
    duration_ms=10042.1,
    timeout_ms=10000,
)
```

### tenacity Integration

Use `tenacity`'s callback hooks to emit standard resilience logs:

```python
import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
)

logger = structlog.get_logger()
stdlib_logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    before_sleep=before_sleep_log(stdlib_logger, logging.WARNING),
    reraise=True,
)
async def fetch_market_data(symbol: str) -> MarketData:
    ...
```

For richer structured logging, implement a custom `before_sleep` callback:

```python
from tenacity import RetryCallState

def log_retry_structured(retry_state: RetryCallState):
    """Emit structured resilience log on each retry."""
    logger.warning(
        "Retrying operation",
        resilience_event="retry_attempt",
        dependency=retry_state.fn.__name__,
        attempt=retry_state.attempt_number,
        duration_ms=retry_state.outcome_timestamp - retry_state.start_time
        if retry_state.outcome_timestamp else None,
        error=str(retry_state.outcome.exception()) if retry_state.outcome else None,
    )
```

### aiobreaker Listener Integration

Register a listener on circuit breakers to emit standard logs:

```python
import aiobreaker

class ResilienceLogger(aiobreaker.CircuitBreakerListener):
    def __init__(self, dependency_name: str):
        self.dependency = dependency_name

    def state_change(self, cb, old_state, new_state):
        event_map = {
            "open": "circuit_breaker_opened",
            "half-open": "circuit_breaker_half_open",
            "closed": "circuit_breaker_closed",
        }
        event = event_map.get(str(new_state), f"circuit_breaker_{new_state}")
        level = "error" if str(new_state) == "open" else "info"
        
        getattr(logger, level)(
            f"Circuit breaker state change: {old_state} → {new_state}",
            resilience_event=event,
            dependency=self.dependency,
            failure_count=cb.fail_counter,
        )

# Attach to breaker
market_data_breaker = aiobreaker.CircuitBreaker(
    fail_max=5,
    timeout_duration=30,
    listeners=[ResilienceLogger("market_data_api")],
)
```

---

## Context Propagation

### The Problem

structlog uses `contextvars` for context binding. `contextvars` propagate automatically across `asyncio.create_task()` and `TaskGroup` boundaries — but **not** across `ThreadPoolExecutor.submit()`, `ProcessPoolExecutor.submit()`, or Taskiq background tasks. Without explicit propagation, `request_id`, `trace_id`, `frontend`, and structlog bindings are silently lost when work crosses these boundaries.

For the full concurrency model and technical details, see **16-core-concurrency-and-resilience.md**. This section defines the observability-specific requirements.

### Propagation Matrix

| Boundary | `request_id` / structlog | OTel `trace_id` / spans | Action |
|----------|--------------------------|------------------------|--------|
| `asyncio.create_task()` | ✅ Automatic | ✅ Automatic | None |
| `asyncio.TaskGroup` | ✅ Automatic | ✅ Automatic | None |
| `asyncio.to_thread()` | ✅ Automatic (3.12+) | ✅ Automatic | None |
| `ThreadPoolExecutor.submit()` | ❌ Lost | ❌ Lost | Use `TracedThreadPoolExecutor` (doc 16) |
| `ProcessPoolExecutor.submit()` | ❌ Lost | ❌ Lost | Pass IDs explicitly, rebind in child |
| `InterpreterPoolExecutor` | ❌ Lost | ❌ Lost | Pass IDs explicitly, rebind in child |
| Taskiq background task | ❌ Lost | ❌ Lost | Pass as task arguments, rebind in worker |
| Redis Streams consumer | ❌ Lost | ❌ Lost | Include in event envelope `correlation_id` field (doc 21) |

### TracedThreadPoolExecutor

All `ThreadPoolExecutor` usage must use the `TracedThreadPoolExecutor` wrapper from doc 16. This propagates both structlog context and OpenTelemetry spans:

```python
import contextvars
from concurrent.futures import ThreadPoolExecutor

class TracedThreadPoolExecutor(ThreadPoolExecutor):
    """ThreadPoolExecutor that propagates contextvars to worker threads."""

    def submit(self, fn, /, *args, **kwargs):
        ctx = contextvars.copy_context()
        return super().submit(ctx.run, fn, *args, **kwargs)
```

### Process Boundary Propagation

For `ProcessPoolExecutor`, serialize and rebind context in the child process:

```python
import structlog

async def compute_in_process(data, request_id: str, trace_id: str | None = None):
    """Run CPU work in process pool with context propagation."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _cpu_pool,
        _compute_with_context,
        data,
        request_id,
        trace_id,
    )

def _compute_with_context(data, request_id: str, trace_id: str | None):
    """Runs in child process — rebind logging and trace context."""
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        source="compute",
    )
    # If OTel is enabled, also restore trace context
    # See Distributed Tracing section for OTel propagation pattern
    
    logger = structlog.get_logger()
    logger.info("Starting computation in child process")
    return _do_compute(data)
```

### Background Task Propagation

For Taskiq tasks (doc 15), pass `request_id` and `correlation_id` as task arguments:

```python
# Dispatching
await tasks["process_signal"].kiq(
    signal_data=data,
    request_id=request.state.request_id,
    correlation_id=str(uuid4()),
)

# Receiving
async def process_signal(
    signal_data: dict,
    request_id: str,
    correlation_id: str,
):
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        correlation_id=correlation_id,
        source="tasks",
    )
    logger = structlog.get_logger()
    logger.info("Processing signal in background task")
    # All subsequent logs include request_id and correlation_id
```

### Event Consumer Propagation

For Redis Streams consumers (doc 21), the `correlation_id` in the event envelope is the link:

```python
async def handle_event(event: dict):
    structlog.contextvars.bind_contextvars(
        correlation_id=event.get("correlation_id"),
        event_type=event.get("event_type"),
        source="events",
    )
    logger = structlog.get_logger()
    logger.info("Processing event")
```

---

## Distributed Tracing

### Standard: OpenTelemetry

All production services use **OpenTelemetry (OTel)** for distributed tracing. This is the third pillar — alongside logs (structlog) and metrics (Prometheus).

Rationale:
- Vendor-neutral standard (CNCF graduated project)
- Native Python instrumentation for FastAPI, httpx, SQLAlchemy, Redis, aiohttp
- W3C Trace Context propagation (`traceparent` header)
- Exports to Tempo, Jaeger, Zipkin, Azure Monitor, or any OTLP-compatible backend
- Correlates with structlog via shared `trace_id` and `span_id`

### What Tracing Answers

Logs tell you *what* happened. Metrics tell you *how much*. Traces tell you *where time went*:

- Which of the five parallel API calls in a `TaskGroup` was slowest?
- How much time was spent waiting for the database vs computing risk?
- Where in the retry chain did the request finally succeed?
- Is the latency in our code, the LLM provider, or the broker API?

### Installation

```
pip install opentelemetry-api opentelemetry-sdk \
    opentelemetry-instrumentation-fastapi \
    opentelemetry-instrumentation-httpx \
    opentelemetry-instrumentation-sqlalchemy \
    opentelemetry-instrumentation-redis \
    opentelemetry-exporter-otlp-proto-grpc
```

### Configuration

Tracing configuration lives in `config/settings/observability.yaml`:

```yaml
tracing:
  enabled: false                    # Enable in staging/production only
  service_name: "${APP_NAME}"
  exporter: "otlp"                  # otlp | jaeger | console
  otlp_endpoint: "http://otel-collector:4317"
  sample_rate: 1.0                  # 1.0 = trace everything, 0.1 = 10%
  
  # Propagation
  propagators:
    - "tracecontext"                # W3C standard
    - "baggage"                     # W3C baggage for cross-service context
```

### Initialization

Set up tracing during application startup:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource

def init_tracing(app: FastAPI, config: dict):
    """Initialize OpenTelemetry tracing. Call during app startup."""
    if not config.get("tracing", {}).get("enabled", False):
        return
    
    resource = Resource.create({
        "service.name": config["tracing"]["service_name"],
        "service.version": APP_VERSION,
        "deployment.environment": APP_ENV,
    })
    
    provider = TracerProvider(resource=resource)
    
    exporter = OTLPSpanExporter(
        endpoint=config["tracing"]["otlp_endpoint"],
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    
    trace.set_tracer_provider(provider)
    
    # Auto-instrument frameworks
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    # Add SQLAlchemy, Redis instrumentation as needed
```

### Correlating Traces with Logs

Inject `trace_id` and `span_id` into structlog context so logs and traces are linked:

```python
import structlog
from opentelemetry import trace

def add_trace_context(logger, method_name, event_dict):
    """structlog processor that adds OTel trace context to every log."""
    span = trace.get_current_span()
    if span and span.is_recording():
        ctx = span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict

# Add to structlog processor chain
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        add_trace_context,                          # <-- Add this
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
```

With this processor, every log entry includes `trace_id` and `span_id`. In Grafana, clicking a trace shows the correlated logs. Clicking a log entry shows the full trace. This is the single most valuable observability integration.

### Custom Spans

Add spans for operations not covered by auto-instrumentation:

```python
tracer = trace.get_tracer(__name__)

async def compute_portfolio_risk(positions: list[Position]) -> RiskMetrics:
    with tracer.start_as_current_span(
        "compute_portfolio_risk",
        attributes={
            "portfolio.positions": len(positions),
            "portfolio.total_value": sum(p.value for p in positions),
        },
    ) as span:
        # Child spans created automatically for DB and HTTP calls
        prices = await fetch_current_prices(positions)
        
        span.set_attribute("risk.computation_method", "monte_carlo")
        risk = await run_monte_carlo(positions, prices)
        
        span.set_attribute("risk.var_95", risk.var_95)
        return risk
```

### Trace Context Propagation Across Processes

For `ProcessPoolExecutor` (doc 16), propagate trace context explicitly:

```python
from opentelemetry.trace.propagation import TraceContextTextMapPropagator

propagator = TraceContextTextMapPropagator()

async def compute_in_process_traced(data, request_id: str):
    """Run CPU work in process pool with full trace propagation."""
    # Inject current trace context into carrier dict
    carrier = {}
    propagator.inject(carrier)
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _cpu_pool,
        _compute_with_trace,
        data,
        request_id,
        carrier,  # Pass serialized trace context
    )

def _compute_with_trace(data, request_id: str, trace_carrier: dict):
    """Runs in child process — restore trace and log context."""
    # Restore structlog context
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        source="compute",
    )
    
    # Restore trace context
    ctx = propagator.extract(trace_carrier)
    with tracer.start_as_current_span("child_computation", context=ctx):
        return _do_compute(data)
```

### Sampling Strategy

Not every request needs a full trace. Configure sampling based on environment:

| Environment | Sample Rate | Rationale |
|-------------|-------------|-----------|
| Development | 1.0 (100%) | Trace everything for debugging |
| Staging | 1.0 (100%) | Full visibility for validation |
| Production (normal) | 0.1 (10%) | Balance visibility with overhead |
| Production (incident) | 1.0 (100%) | Temporary increase during debugging |

**Always trace errors:** Configure a parent-based sampler that traces 100% of errored requests regardless of the base sample rate.

### What to Trace

**Always instrument (auto-instrumentation covers these):**
- HTTP requests (FastAPI, httpx)
- Database queries (SQLAlchemy async)
- Redis operations
- gRPC calls (if applicable)

**Add custom spans for:**
- CPU-bound operations in process/thread pools
- LLM provider calls (model, tokens, latency)
- Circuit breaker decisions
- Business-critical operations (order placement, signal generation)

**Do not trace:**
- Health check endpoints (noisy, useless)
- Prometheus `/metrics` scrape endpoint
- Static file serving

---

## Health Checks

### Endpoint Structure

Three health endpoints implemented in `modules/backend/api/health.py`:

**`GET /health`** - Liveness
- Returns 200 if process is running
- No dependency checks
- Used by process monitors (Kubernetes liveness probe)
- **Never checks external dependencies** — a liveness probe that queries the database will kill your pods when the database is slow
- Response: `{"status": "healthy"}`

**`GET /health/ready`** - Readiness
- Returns 200 if ready to serve traffic
- Checks critical dependencies (database, Redis) in parallel
- **Reports circuit breaker states** — if a critical dependency's circuit breaker is open, readiness degrades
- Used by load balancers (Kubernetes readiness probe)
- Returns 503 if any configured dependency is unhealthy or if the service is shutting down (see doc 16 graceful shutdown)

**`GET /health/detailed`** - Component Status
- Returns comprehensive status of each component
- Includes latency measurements
- **Includes circuit breaker state for every external dependency**
- **Includes concurrency pool utilization** (thread pool, process pool, semaphore availability)
- Should be protected by authentication in production
- Used for debugging and monitoring dashboards

### Response Format

```json
{
  "status": "healthy",
  "application": {
    "name": "trading-platform",
    "env": "production",
    "version": "1.0.0"
  },
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5
    },
    "redis": {
      "status": "healthy",
      "latency_ms": 1
    }
  },
  "circuit_breakers": {
    "market_data_api": {
      "state": "closed",
      "failure_count": 0,
      "last_failure": null
    },
    "broker_api": {
      "state": "half_open",
      "failure_count": 3,
      "last_failure": "2026-03-01T10:15:30Z",
      "recovery_at": "2026-03-01T10:16:00Z"
    },
    "llm_provider": {
      "state": "open",
      "failure_count": 5,
      "last_failure": "2026-03-01T10:14:55Z",
      "recovery_at": "2026-03-01T10:15:55Z"
    }
  },
  "pools": {
    "thread_pool": {
      "max_workers": 10,
      "active_workers": 3,
      "pending_tasks": 0
    },
    "process_pool": {
      "max_workers": 4,
      "active_workers": 1,
      "pending_tasks": 0
    },
    "semaphores": {
      "market_data": {"capacity": 20, "available": 17},
      "llm_provider": {"capacity": 5, "available": 5},
      "database": {"capacity": 50, "available": 48}
    }
  },
  "timestamp": "2026-03-01T12:00:00Z"
}
```

### Status Values

| Status | Meaning |
|--------|---------|
| `healthy` | Component is working correctly |
| `unhealthy` | Component is failing |
| `degraded` | Component is operational but impaired (e.g., circuit breaker half-open) |
| `not_configured` | Component not enabled (OK for optional dependencies) |

### Health Check Implementation

- Checks run in parallel for fast response (use `asyncio.TaskGroup`)
- Use simple queries (SELECT 1, PING)
- Total response time should be < 1 second
- Fail open for non-critical dependencies
- **Liveness probes NEVER check external dependencies** — only that the process is alive
- **Readiness probes check critical dependencies** — database, Redis, critical circuit breakers

---

## Metrics (Production)

### Application Metrics

Track these metrics for all services:

**Request metrics:**
- Request count by endpoint, method, status, and frontend
- Request duration (p50, p95, p99)
- Request size
- Error rate by type

**System metrics:**
- CPU usage
- Memory usage
- Disk usage
- Open file descriptors

**Business metrics:**
- Active users
- Operations per period
- Queue depths
- Cache hit rates

**Resilience metrics:**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `circuit_breaker_state` | Gauge | `dependency` | 0=closed, 1=half-open, 2=open |
| `circuit_breaker_transitions_total` | Counter | `dependency`, `from_state`, `to_state` | State transition count |
| `retry_attempts_total` | Counter | `dependency`, `outcome` (success/failure) | Total retry attempts |
| `timeout_exceeded_total` | Counter | `dependency` | Timeout breach count |
| `bulkhead_rejections_total` | Counter | `dependency` | Calls rejected by full semaphore |

**Concurrency metrics:**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `executor_active_workers` | Gauge | `pool_type` (thread/process) | Currently busy workers |
| `executor_pending_tasks` | Gauge | `pool_type` | Tasks waiting for a worker |
| `executor_max_workers` | Gauge | `pool_type` | Pool capacity |
| `semaphore_available` | Gauge | `dependency` | Remaining semaphore slots |
| `active_async_tasks` | Gauge | | Currently running asyncio tasks |

### Metric Format

Use Prometheus format for metrics:
- Counter for cumulative values
- Gauge for current values
- Histogram for distributions
- Labels for dimensions (including `frontend` from X-Frontend-ID)

### Prometheus Integration (Production)

For production deployments, expose a `/metrics` endpoint:

```python
# pip install prometheus-fastapi-instrumentator
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
```

### Multi-Process Prometheus

When running multiple Uvicorn workers (docs 17, 22), each worker is a separate process with its own metric registry. Without coordination, metrics from different workers conflict and produce incorrect aggregates.

**Standard approach:**

```python
import os
from prometheus_client import CollectorRegistry, multiprocess, generate_latest

# Set before importing any prometheus_client metrics
os.environ["PROMETHEUS_MULTIPROC_DIR"] = "/tmp/prometheus_multiproc"

# Clean up stale files on startup
if os.path.exists("/tmp/prometheus_multiproc"):
    import shutil
    shutil.rmtree("/tmp/prometheus_multiproc")
os.makedirs("/tmp/prometheus_multiproc", exist_ok=True)

# In your /metrics endpoint
@app.get("/metrics")
async def metrics():
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return Response(
        generate_latest(registry),
        media_type="text/plain",
    )
```

**Alternative:** Use `pytheus` instead of `prometheus_client` — it handles multi-process metric collection natively without `PROMETHEUS_MULTIPROC_DIR`. Evaluate if the standard `prometheus_client` approach becomes problematic.

### Custom Resilience Metrics Implementation

```python
from prometheus_client import Gauge, Counter

# Circuit breaker metrics
cb_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    ["dependency"],
)
cb_transitions = Counter(
    "circuit_breaker_transitions_total",
    "Circuit breaker state transitions",
    ["dependency", "from_state", "to_state"],
)

# Update on state change (in ResilienceLogger from Resilience Event Logging section)
def update_breaker_metrics(dependency: str, old_state: str, new_state: str):
    state_map = {"closed": 0, "half-open": 1, "open": 2}
    cb_state.labels(dependency=dependency).set(state_map.get(new_state, -1))
    cb_transitions.labels(
        dependency=dependency,
        from_state=old_state,
        to_state=new_state,
    ).inc()
```

---

## Error Tracking

### Error Capture

All unhandled exceptions captured with:
- Full stack trace
- Request context (URL, method, user, request_id, frontend)
- **Trace context** (trace_id, span_id — for correlation with distributed traces)
- Environment information
- Application version

### Error Grouping

Group related errors:
- By exception type and location
- By error message pattern
- Track occurrence count and timeline

### Error Alerting

Alert on:
- New error types (not seen before)
- Error rate exceeds threshold
- Critical errors (always)
- **Circuit breaker state changes** (always — a breaker opening means a dependency is failing)

---

## Alerting (Production)

### Alert Categories

| Category | Response Time | Examples |
|----------|---------------|----------|
| Critical | Immediate | Service down, data loss risk, **circuit breaker open on critical dependency** |
| Warning | Hours | High error rate, resource pressure, **circuit breaker half-open**, **retry rate spike** |
| Info | Next business day | Unusual patterns, approaching limits |

### Alert Channels

- Critical: SMS/phone + email
- Warning: Email + chat (Slack/Discord)
- Info: Email or dashboard

### Grafana Alerting

For production deployments, configure alerts in Grafana:

```yaml
# Example alert rules

# High error rate
- alert: HighErrorRate
  expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
  for: 5m
  labels:
    severity: warning

# Circuit breaker opened
- alert: CircuitBreakerOpen
  expr: circuit_breaker_state > 1
  for: 0m
  labels:
    severity: critical
  annotations:
    summary: "Circuit breaker open for {{ $labels.dependency }}"

# Retry rate spike
- alert: HighRetryRate
  expr: rate(retry_attempts_total[5m]) > 10
  for: 5m
  labels:
    severity: warning

# Thread pool saturation
- alert: ExecutorPoolSaturation
  expr: executor_active_workers / executor_max_workers > 0.9
  for: 5m
  labels:
    severity: warning
```

---

## Profiling

### Why Standard Profilers Fail for Async Code

Statistical profilers like cProfile and py-spy sample the call stack at regular intervals. For synchronous code, this accurately shows where CPU time is spent. For async code, coroutines suspended on `await` appear as *not running* — the profiler doesn't see them. This means the actual bottleneck (a slow external API call, a backed-up semaphore, a stuck database query) is invisible to standard profiling.

Use the right tool for the right problem:

| Tool | Use Case | Overhead | Async-Aware | Production-Safe |
|------|----------|----------|-------------|-----------------|
| `py-spy` | Thread stacks, deadlocks, CPU hot paths | Near-zero (sampling) | ❌ (sees OS threads, not coroutines) | ✅ |
| `yappi` | Deterministic async profiling, wall-clock per coroutine | Moderate (2–5x) | ✅ | ⚠️ Staging only |
| `Scalene` | Line-level CPU + memory, leak detection | Low–moderate | ❌ | ⚠️ Staging only |
| `asyncio pstree` | Live async task tree, stuck coroutine identification | None (snapshot) | ✅ | ✅ |

### py-spy: First Tool for Production Issues

py-spy attaches to a running Python process without restart, instrumentation, or code changes. Zero overhead when not attached.

```bash
# Installation (one-time, on production hosts)
pip install py-spy

# Dump all thread stacks — diagnose deadlocks, stuck requests
py-spy dump --pid <PID>

# Record flame graph for 30 seconds
py-spy record -o profile.svg --pid <PID> --duration 30

# Top-like live view — see where CPU time is spent right now
py-spy top --pid <PID>

# Profile a specific subcommand from start
py-spy record -o startup.svg -- python cli.py --service worker
```

**This is your first tool** when a production service is slow, stuck, or consuming unexpected CPU. Use `py-spy dump` to get a thread-level snapshot: if all threads are waiting on the same lock, you have a contention problem. If a thread is stuck in a C extension call, you know the bottleneck is in native code. If threads are idle but the service is slow, the bottleneck is in async code — switch to `asyncio pstree`.

### asyncio Introspection (3.14+)

Python 3.14 added built-in async task inspection. No installation, no instrumentation, no overhead.

```bash
# List all running async tasks — name, coroutine, state
python -m asyncio ps <PID>

# Show task parent/child tree — which task spawned which
python -m asyncio pstree <PID>
```

**Use this when py-spy shows idle threads but the service is slow.** The event loop is running in one thread — py-spy sees it as one stack. `asyncio pstree` shows you every coroutine inside that event loop: which are running, which are waiting, and what they're waiting on.

**Typical diagnosis workflow:**
1. Service is slow → `py-spy dump --pid <PID>` → threads look normal (all in `select`/`epoll`)
2. Async bottleneck suspected → `python -m asyncio pstree <PID>` → 200 tasks awaiting `_price_semaphore`
3. Root cause: semaphore capacity too low for request volume → increase in `concurrency.yaml`

### yappi: Deterministic Async Profiling

When you need exact call counts and per-coroutine wall-clock time (not sampling estimates), use yappi. It correctly attributes time across `await` boundaries.

```python
import yappi

# Start profiling (wall clock for async, CPU clock for sync)
yappi.set_clock_type("wall")
yappi.start()

# ... run your workload for a controlled period ...

yappi.stop()

# Print function stats sorted by total time
stats = yappi.get_func_stats()
stats.sort("totaltime", "desc")
stats.print_all(columns={
    0: ("name", 80),
    1: ("ncall", 10),
    2: ("tsub", 8),   # Time in function itself
    3: ("ttot", 8),   # Total time including callees
})

# Export for flamegraph visualization
stats.save("profile.pstat", type="pstat")
```

**When to use yappi vs py-spy:**
- py-spy: "Something is slow in production right now" → attach and observe
- yappi: "I want to find the hot path in this async workflow" → run controlled benchmark in staging

**Do not run yappi in production.** Its deterministic instrumentation adds 2–5x overhead. Use it in staging with representative load.

### Scalene: Memory Profiling

For detecting memory leaks in long-running services:

```bash
scalene --cpu --memory --reduced-profile my_service.py
```

Scalene distinguishes Python memory allocations from native library allocations (numpy, pandas) and shows line-by-line memory growth. Use when a service's RSS grows continuously over hours — structlog, database connection pools, and in-memory caches are common culprits.

---

## Telemetry Debug API

Per-session verbose logging without affecting global log levels or other users. This replaces the "Future Enhancements" placeholder from version 2.0.0.

### Purpose

When debugging a production issue, you need detailed logs for one specific session without:
- Enabling DEBUG globally (too noisy, fills disks, slows the service)
- Affecting other users' performance
- Restarting the application
- Deploying a code change

### Endpoint

**`POST /api/telemetry/debug`** (authenticated, admin/developer role required)

**Request:**
```json
{
  "enable": true,
  "duration_minutes": 15,
  "frontend_id": "web",
  "scope": "all"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable` | bool | required | Enable or disable debug mode |
| `duration_minutes` | int | 15 | Token TTL (max 60 minutes) |
| `frontend_id` | string | null | Filter to specific frontend (null = all) |
| `scope` | string | "all" | `all`, `resilience`, `database`, `external` |

**Response:**
```json
{
  "debug_token": "dbg_a1b2c3d4e5f6...",
  "expires_at": "2026-03-01T12:15:00Z",
  "instructions": "Add X-Debug-Token header to requests"
}
```

### How It Works

1. Client requests debug token via authenticated endpoint
2. Server generates token, stores in Redis with TTL matching `duration_minutes`
3. Client includes `X-Debug-Token: dbg_a1b2c3d4e5f6...` header in subsequent requests
4. Middleware detects token, enables verbose logging for that request only:
   - DEBUG level logging instead of INFO
   - Detailed timing breakdown per middleware and handler
   - Database query text (without parameter values)
   - External API call details (URL, headers minus auth, response time)
   - Resilience event details (breaker state, retry count, backoff duration)
   - Request/response bodies (sanitized — PII and auth tokens stripped)
5. Token expires automatically — no cleanup required

### Implementation Requirements

- Token storage: Redis with TTL (reuses existing Redis from doc 15)
- Middleware enhancement: Check for `X-Debug-Token` header, validate against Redis
- Output sanitization: Strip passwords, API keys, bearer tokens, PII from debug output
- Rate limiting: Maximum 5 active debug tokens per environment
- Audit logging: Log who enabled debug mode, when, and for which scope
- Authentication: Requires admin or developer role (doc 06)

### Security Considerations

- Debug output must be sanitized — never expose credentials or PII, even in debug mode
- Tokens have short TTLs (max 60 minutes)
- Audit trail for compliance: every debug session is logged with activator identity
- Disable in development environments (use `APP_DEBUG=true` instead — simpler, no token needed)

---

## Performance Monitoring

### Slow Query Detection

Log queries exceeding threshold:
- Default threshold: 100ms
- Include query (without parameters), duration, caller
- Include `request_id` and `trace_id` for correlation
- Review periodically, add indexes or optimize

### Slow Request Detection

Log requests exceeding threshold:
- Default threshold: 1 second
- Include endpoint, method, duration, user, frontend
- Breakdown by component (database, external calls, computation)
- Include `trace_id` — one click to see the full trace breakdown

### Resource Monitoring

Monitor and alert on:
- Database connection pool exhaustion
- Redis memory usage
- Disk space
- Process memory growth
- **Thread pool saturation** (active workers / max workers > 90%)
- **Process pool saturation** (active workers / max workers > 90%)
- **Semaphore exhaustion** (available / capacity < 10%)
- **Open file descriptors** (critical on macOS — default limit 256, see doc 16)

---

## Debugging

### Debug Mode

Applications support debug mode:
- Enabled via `APP_DEBUG=true` environment variable
- More verbose logging (DEBUG level)
- Detailed error responses (development only)
- Performance profiling available

### Debug Mode vs Telemetry Debug API

| | `APP_DEBUG=true` | Telemetry Debug API |
|--|-----------------|-------------------|
| Scope | Entire application | Single session/request |
| Environment | Development/staging only | Production-safe |
| Activation | Env var (requires restart) | API call (no restart) |
| Duration | Permanent until disabled | Auto-expires (max 60 min) |
| Authentication | None | Required (admin/developer) |
| Audit trail | None | Full audit logging |

### Log Level Override

Runtime log level changes:
- Via `LOG_LEVEL` environment variable (requires restart)
- Via Telemetry Debug API (no restart, per-session, auto-expires)

### Request Debugging

For specific request troubleshooting:
1. Use `X-Request-ID` to trace through logs
2. Use `trace_id` to find the full distributed trace in Tempo/Jaeger
3. Filter logs by `X-Frontend-ID` to isolate frontend issues
4. Check `X-Response-Time` header for performance issues
5. Use Telemetry Debug API for verbose per-session logging
6. Use `python -m asyncio pstree <PID>` to inspect stuck async tasks

---

## Dashboards (Production)

### Essential Dashboards

**Operations Dashboard:**
- Service health status (from `/health` endpoints)
- Request rate and latency by frontend
- Error rate by type and frontend
- Resource utilization
- **Circuit breaker states** (red=open, yellow=half-open, green=closed)
- **Executor pool utilization** (thread and process pools)
- **Semaphore saturation** per dependency

**Resilience Dashboard:**
- Circuit breaker state timeline per dependency
- Retry rate per dependency
- Timeout rate per dependency
- Bulkhead rejection rate per dependency
- Mean time to recovery (breaker open → closed)

**Trace Dashboard:**
- Request duration distribution (p50, p95, p99)
- Slowest traces (top 10 by duration)
- Error traces (grouped by root cause)
- Dependency latency breakdown (time in DB vs API vs compute)

**Business Dashboard:**
- Active users by frontend
- Key business metrics
- Trend comparisons

### Grafana Setup

For production deployments, use Grafana with:
- Prometheus as metrics data source
- Loki as logs data source
- **Tempo as traces data source** (or Jaeger)
- Pre-built dashboards for FastAPI applications
- **Trace-to-log and log-to-trace links** configured via Grafana data source correlation

---

## Production Deployment Stack

### Recommended Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| Traces | **OpenTelemetry SDK + Collector** | Distributed trace generation and collection |
| Trace Storage | **Tempo** (or Jaeger) | Trace storage and querying |
| Metrics | Prometheus | Time-series metrics collection |
| Logs | Loki | Log aggregation and querying |
| Dashboards | Grafana | Visualization and alerting |
| Log Shipping | Promtail | Ship logs to Loki |

### Azure Deployment

For Azure-hosted services (doc 18), use Azure Monitor as an alternative backend:

```
pip install opentelemetry-exporter-azuremonitor
```

```python
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

exporter = AzureMonitorTraceExporter(
    connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
)
```

This replaces the `OTLPSpanExporter` in the initialization code. All instrumentation, custom spans, and context propagation remain identical — only the exporter changes.

### Deployment Notes

This stack is **not included in the skeleton code**. It's infrastructure that should be deployed separately:

1. **Development**: Use local logs in `logs/`, `console` trace exporter for debugging, no metrics infrastructure needed. Use `py-spy` and `asyncio pstree` for profiling.
2. **Staging**: Deploy full stack (OTel Collector + Tempo + Prometheus + Loki + Grafana). Enable 100% trace sampling. Run yappi benchmarks.
3. **Production**: Same stack as staging. Adjust trace sampling rate (10% default, increase during incidents). Deploy py-spy for on-demand profiling.

The skeleton provides the hooks (structured logs, OTel instrumentation, health endpoints, request context, resilience event logging, metrics registration) that integrate with this stack.

---

## Log Retention

### Retention Policy

| Log Type | Retention |
|----------|-----------|
| Application logs | 30 days |
| Access logs | 90 days |
| Audit logs | 1 year minimum |
| Debug logs (Telemetry API) | 7 days |
| Traces | 14 days (adjust based on storage cost) |

Adjust based on compliance requirements.

### Log Archival

After retention period:
- Compress and archive to cold storage
- Or delete if not required

Implement automated cleanup to prevent disk exhaustion.

---

## Runbooks

### Runbook Content

For each alert type, document:
- What the alert means
- Potential causes
- Investigation steps (include specific tool commands — py-spy, asyncio pstree, jq filters)
- Resolution procedures
- Escalation path

### Runbook Location

Store runbooks with documentation:
- Version controlled
- Linked from alerts
- Reviewed and updated regularly

### Essential Runbooks

| Alert | First Investigation Step |
|-------|------------------------|
| Service unresponsive | `py-spy dump --pid <PID>` — check for deadlocks or blocked threads |
| High latency, low CPU | `python -m asyncio pstree <PID>` — check for stuck coroutines or semaphore contention |
| High latency, high CPU | `py-spy record -o profile.svg --pid <PID> --duration 30` — find CPU hot path |
| Circuit breaker open | Check Grafana resilience dashboard → identify failing dependency → check dependency status |
| Memory growing | `scalene --memory` in staging with representative load → identify leaking allocations |
| Thread pool saturated | Check `executor_active_workers` metric → identify slow blocking operations → consider increasing pool size or fixing the blocking call |

---

## Configuration

All observability settings centralized in `config/settings/observability.yaml`:

```yaml
logging:
  level: "INFO"                     # Override with LOG_LEVEL env var
  format: "json"                    # json | human (human for development)
  file: "logs/system.jsonl"
  max_bytes: 10485760               # 10MB
  backup_count: 5

tracing:
  enabled: false                    # Enable in staging/production
  service_name: "${APP_NAME}"
  exporter: "otlp"                  # otlp | azuremonitor | console
  otlp_endpoint: "http://otel-collector:4317"
  azure_connection_string: ""       # For Azure Monitor exporter
  sample_rate: 1.0
  propagators:
    - "tracecontext"
    - "baggage"

metrics:
  enabled: false                    # Enable in staging/production
  multiprocess_dir: "/tmp/prometheus_multiproc"

debug_api:
  enabled: true                     # Always enabled (auth-gated)
  max_active_tokens: 5
  max_duration_minutes: 60
  redis_key_prefix: "debug_token:"

health_checks:
  ready_timeout_seconds: 5
  detailed_auth_required: true
```

---

## Dependencies on Other Documents

| Document | Relationship |
|----------|-------------|
| 02-core-principles.md | O1 (Observable by Default) — this doc is the implementation |
| 04-core-backend-architecture.md | Request context middleware, health check integration |
| 21-opt-event-architecture.md | `correlation_id` in event envelope links to request traces |
| 30-ai-llm-integration.md | LLM-specific circuit breaker and cost metrics reference this doc's resilience logging contract |
| 06-core-authentication.md | Telemetry Debug API requires admin/developer role |
| 13-core-security-standards.md | Security event logging feeds into audit trail |
| 15-core-background-tasks.md | Context propagation for Taskiq workers |
| 17-core-deployment-bare-metal.md | Production stack deployment (Prometheus, Loki, Grafana, Tempo) |
| 18-core-deployment-azure.md | Azure Monitor exporter configuration |
| 16-core-concurrency-and-resilience.md | `TracedThreadPoolExecutor`, process context propagation, resilience patterns, profiling tools |
| 31-ai-agentic-architecture.md | Agent task tracing, cost tracking observability |
| 32-ai-agentic-pydanticai.md | Agent execution tracing, structlog.contextvars patterns |
