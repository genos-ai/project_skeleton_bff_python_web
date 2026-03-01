# 16 — Concurrency, Parallelism, and Resilience

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-03-01*

## Changelog

- 1.0.0 (2026-03-01): Initial document — Python 3.14 upgrade, in-process concurrency patterns, uvloop, resilience layers, context propagation, graceful shutdown, platform guidance

---

## Purpose

This document defines standards for concurrent execution, parallel processing, and resilience patterns. It is a **Core** standard — every backend service makes concurrent calls and needs resilience against external failures.

---

## Context

The reference architecture standardized background tasks (15) and event-driven communication (21) but left a gap: what happens *inside* a single process when it needs to do multiple things at once, handle CPU-bound work, survive external failures, and maintain observability across all of it.

This gap matters because the architecture's primary workloads — trading signal processing, LLM orchestration (31, 32), multi-channel delivery (27), and real-time data pipelines — are all concurrency-intensive. A trading signal that takes 200ms because API calls run sequentially instead of in parallel is a trading signal that arrives too late. An LLM call that retries without backoff or a circuit breaker hammers a failing provider and cascades the failure to every other request in the process.

The existing standards touch concurrency in fragments: doc 04 mentions `asyncio.TaskGroup` briefly, doc 30 defines a circuit breaker for LLM calls only, doc 08 standardizes structlog but doesn't address context propagation across threads or processes, and doc 15 handles out-of-process task queues. This document consolidates concurrency into a single prescriptive standard, extracts resilience from its LLM-specific silo into a cross-cutting pattern, and addresses the Python 3.14 upgrade that unlocks the next generation of concurrency primitives.

Every decision here optimizes for the same thing: **lowest safe latency with full observability**. If you can't trace it, you can't trust it. If you can't trust it, you can't trade with it.

---

## Python Version

### Standard: Python 3.14

All new projects target **Python 3.14**. Existing projects on 3.12 should upgrade during their next major release cycle.

Rationale:
- **5–10% general performance improvement** over 3.12 (specializing adaptive interpreter, PEP 659)
- **`InterpreterPoolExecutor`** — true parallelism within a single process via sub-interpreters (PEP 734)
- **`asyncio` introspection CLI** — `python -m asyncio ps <PID>` and `pstree <PID>` for live debugging of stuck services
- **`ProcessPoolExecutor.terminate_workers()`** and **`kill_workers()`** — explicit worker lifecycle control
- **`Executor.map()` `buffersize` parameter** — prevents memory blowup with large iterables
- **`forkserver` default on Linux** — safe multiprocessing in threaded contexts
- **Free-threaded build available** (experimental, not default) — enables true multi-threaded CPU parallelism without the GIL

### Upgrade Path from 3.12

1. Update `pyproject.toml` / `requirements.txt` to `python_requires >= 3.14`
2. Replace deprecated `asyncio.get_event_loop()` calls with `asyncio.run()` or `asyncio.Runner` — 3.14 raises `RuntimeError` if no running loop exists
3. Update deployment configs: doc 17 systemd units, doc 18 Azure `pythonVersion` and `runtimeStack`
4. Run full test suite — no code changes expected for pure Python; test C-extension dependencies
5. Enable `uvloop` (see below)

### Free-Threaded Build (3.14t)

The free-threaded build removes the GIL, enabling true multi-threaded CPU parallelism. As of early 2026:

- **Single-thread penalty:** 5–10% (down from 40% in 3.13t)
- **CPU-bound scaling:** up to 7.2x on 8 cores
- **Ecosystem coverage:** ~60 of top 360 C-extension packages (NumPy, pandas, scikit-learn, PyTorch supported; Polars, grpcio, protobuf not yet)
- **Status:** Supported but not default (PEP 779). Default projected for Python 3.18+

**Decision:** Do not use free-threaded builds in production yet. Use `ProcessPoolExecutor` or `InterpreterPoolExecutor` for CPU-bound parallelism. Re-evaluate when free-threading becomes the default build.

**Exception:** Internal tooling and benchmarking may use 3.14t for experimentation where the dependency chain is fully controlled.

---

## Concurrency Model

### The Three Mechanisms

Python provides three concurrency mechanisms. Each solves a different problem. Using the wrong one is worse than using none.

| Mechanism | Best For | Parallelism | Shared State | Overhead |
|-----------|----------|-------------|--------------|----------|
| `asyncio` (coroutines) | I/O-bound: HTTP calls, database queries, WebSocket | Concurrent, not parallel | Full (single thread) | Negligible |
| `threading` / `ThreadPoolExecutor` | Blocking I/O that lacks async support | Concurrent (GIL-limited for CPU) | Full (requires locks) | Low |
| `multiprocessing` / `ProcessPoolExecutor` | CPU-bound: computation, data processing | True parallel | None (IPC required) | High (process creation) |

### Decision Matrix

| Workload | Standard Approach | Expected Gain |
|----------|-------------------|---------------|
| Multiple HTTP/API calls | `asyncio.TaskGroup` | 3–10x vs sequential |
| Database queries + API calls | `asyncio.TaskGroup` | 2–5x vs sequential |
| Blocking library without async API | `asyncio.to_thread()` | Unblocks event loop |
| CPU-bound computation (single machine) | `ProcessPoolExecutor` | Near-linear to core count |
| CPU-bound with shared numpy arrays | `ProcessPoolExecutor` + `shared_memory` | Near-linear, zero-copy |
| Mixed I/O + CPU in one service | asyncio + `ProcessPoolExecutor` via `loop.run_in_executor()` | Best of both |
| High-throughput network server | asyncio + `uvloop` | 2–4x over default loop |
| Distributed compute across machines | Ray (external, not in-process) | Near-linear across cluster |

### What Not To Do

- **Never use `threading` for CPU-bound work.** The GIL serializes CPU-bound threads. You get overhead with no parallelism.
- **Never use `asyncio.gather()` when all tasks must succeed.** Use `TaskGroup` — it cancels siblings on first failure. `gather()` lets orphaned tasks leak.
- **Never call blocking functions directly in async code.** Wrap with `asyncio.to_thread()` or run in an executor. A single blocking call stalls the entire event loop.
- **Never use `multiprocessing.Pool` in new code.** Use `ProcessPoolExecutor` — cleaner error handling, context manager support, consistent API with `ThreadPoolExecutor`.
- **Never use `fork` start method explicitly.** It is unsafe in threaded processes. Linux defaults to `forkserver` in 3.14; macOS defaults to `spawn`. Do not override these.

---

## asyncio Patterns

### Standard Event Loop: uvloop

All FastAPI services use `uvloop` as the asyncio event loop.

Rationale:
- **2–4x faster** than the default asyncio event loop (benchmarked at ~105K req/s on echo servers)
- Built on libuv (Node.js's battle-tested I/O library)
- Drop-in replacement — no code changes required
- Works on both macOS and Linux with equivalent performance
- Adopted by Microsoft Azure Functions as default for Python 3.13+

**Installation:**
```
pip install uvloop
```

**Configuration in FastAPI (via Uvicorn):**
```bash
uvicorn modules.backend.main:app --loop uvloop --host 0.0.0.0 --port 8000
```

Or programmatically in `main.py`:
```python
import uvloop

uvloop.install()  # Call before any asyncio usage
```

**Do not use uvloop** when debugging event loop internals (it's a Cython extension, harder to step through).

### TaskGroup (Structured Concurrency)

`asyncio.TaskGroup` is the **only** pattern for parallel async operations where all must succeed. This supersedes the brief mention in doc 04.

```python
import asyncio

async def get_trading_signals(symbols: list[str]) -> list[Signal]:
    """Fetch signals for multiple symbols in parallel."""
    async with asyncio.timeout(5):  # Hard wall-clock limit
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(fetch_signal(s), name=f"signal-{s}")
                for s in symbols
            ]

    return [t.result() for t in tasks]
```

**Behaviour on failure:** If any task raises, all sibling tasks are cancelled. All exceptions are collected into an `ExceptionGroup`. Handle with `except*`:

```python
try:
    async with asyncio.TaskGroup() as tg:
        tg.create_task(risky_operation_a())
        tg.create_task(risky_operation_b())
except* ValueError as eg:
    for exc in eg.exceptions:
        logger.error("Validation failed", error=str(exc))
except* TimeoutError as eg:
    logger.error("Operations timed out", count=len(eg.exceptions))
```

### Best-Effort Parallel Operations

When some failures are acceptable (e.g., fetching optional enrichment data), use `asyncio.gather()` with `return_exceptions=True`:

```python
results = await asyncio.gather(
    fetch_price(symbol),
    fetch_news(symbol),       # Optional — failure is OK
    fetch_sentiment(symbol),  # Optional — failure is OK
    return_exceptions=True,
)

price = results[0]  # Required — raise if exception
if isinstance(price, Exception):
    raise price

news = results[1] if not isinstance(results[1], Exception) else None
sentiment = results[2] if not isinstance(results[2], Exception) else None
```

### Concurrency Limiting with Semaphore

All external service calls must be concurrency-limited. Unbounded parallelism against an external API is a denial-of-service attack on your own dependency.

```python
# Module-level semaphores — one per external dependency
_market_data_semaphore = asyncio.Semaphore(24)   # Max 20 concurrent calls
_llm_semaphore = asyncio.Semaphore(5)            # Max 5 concurrent LLM calls
_database_semaphore = asyncio.Semaphore(50)      # Max 50 concurrent queries

async def fetch_market_data(symbol: str) -> MarketData:
    async with _market_data_semaphore:
        async with asyncio.timeout(07):
            return await market_client.get(symbol)
```

**Semaphore sizing guidance:**

| Dependency | Starting Value | Adjust Based On |
|-----------|----------------|-----------------|
| External REST API | 10–20 | Provider rate limits |
| LLM provider | 3–10 | Token budget, latency requirements |
| Database pool | Match pool size | Connection pool `max_size` |
| Redis | 50–100 | Redis `maxclients` setting |
| Internal microservice | 20–50 | Target service capacity |

### Blocking Operations

Any synchronous/blocking call in async code **must** be offloaded:

```python
import asyncio

# File I/O (synchronous in CPython)
content = await asyncio.to_thread(Path("data.csv").read_text)

# CPU-bound computation
result = await asyncio.to_thread(compute_technical_indicators, prices)

# Blocking third-party library
data = await asyncio.to_thread(blocking_sdk.fetch, params)
```

`asyncio.to_thread()` runs the function in the default `ThreadPoolExecutor`. For CPU-bound work that exceeds 50ms, use `ProcessPoolExecutor` instead (see next section).

### Eager Task Execution (3.12+)

Enable eager task execution for services with many short-lived coroutines (cached lookups, memoized results):

```python
import asyncio

loop = asyncio.get_running_loop()
loop.set_task_factory(asyncio.eager_task_factory)
```

Tasks that complete synchronously (cache hits, already-resolved futures) skip event loop scheduling entirely. Benchmarks show **2–5x speedup** for these patterns.

---

## CPU-Bound Parallelism

### ProcessPoolExecutor

For CPU-intensive work — technical indicator computation, risk calculations, data transformation, model inference — use `ProcessPoolExecutor`:

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

# Create once at module level, reuse across requests
_cpu_pool = ProcessPoolExecutor(max_workers=4)

async def compute_portfolio_risk(positions: list[Position]) -> RiskMetrics:
    """Run CPU-intensive risk calculation in process pool."""
    loop = asyncio.get_running_loop()
    
    # Serialize input, run in separate process
    result = await loop.run_in_executor(
        _cpu_pool,
        _calculate_risk,  # Must be a top-level function (picklable)
        positions,
    )
    return result

def _calculate_risk(positions: list[Position]) -> RiskMetrics:
    """Pure CPU work — runs in child process."""
    # Monte Carlo simulation, VaR calculation, etc.
    ...
```

**Worker count guidance:**

| Workload | Workers | Rationale |
|----------|---------|-----------|
| Pure CPU computation | `os.cpu_count() - 1` | Leave one core for the event loop |
| Mixed CPU + I/O service | `os.cpu_count() // 2` | Balance between async and compute |
| Memory-heavy computation | 2–4 regardless of cores | Each worker duplicates memory |

**Always set `max_workers` explicitly.** The default (`os.cpu_count() + 4` for threads, `os.cpu_count()` for processes) is rarely optimal.

### Shared Memory for Large Data

When passing large arrays between processes, avoid serialization overhead with `multiprocessing.shared_memory`:

```python
import numpy as np
from multiprocessing.shared_memory import SharedMemory

def create_shared_array(data: np.ndarray) -> tuple[str, tuple, str]:
    """Create shared memory block from numpy array."""
    shm = SharedMemory(create=True, size=data.nbytes)
    shared_array = np.ndarray(data.shape, dtype=data.dtype, buffer=shm.buf)
    np.copyto(shared_array, data)
    return shm.name, data.shape, str(data.dtype)

def read_shared_array(name: str, shape: tuple, dtype: str) -> np.ndarray:
    """Read numpy array from shared memory (zero-copy)."""
    shm = SharedMemory(name=name, create=False)
    return np.ndarray(shape, dtype=np.dtype(dtype), buffer=shm.buf)
```

**Rules:**
- Only the creator calls `shm.unlink()`
- All consumers call `shm.close()` when done
- Use `SharedMemoryManager` with context managers for automatic lifecycle
- Protect concurrent writes with `multiprocessing.Lock`

### InterpreterPoolExecutor (3.14+)

Python 3.14 introduced `InterpreterPoolExecutor` — sub-interpreters with independent GILs running in threads within the same process. This provides process-level isolation with thread-level efficiency.

```python
from concurrent.futures import InterpreterPoolExecutor

_interp_pool = InterpreterPoolExecutor(max_workers=4)

async def compute_signals(symbols: list[str]) -> list[Signal]:
    loop = asyncio.get_running_loop()
    futures = [
        loop.run_in_executor(_interp_pool, compute_signal, sym)
        for sym in symbols
    ]
    return await asyncio.gather(*futures)
```

**When to use InterpreterPoolExecutor over ProcessPoolExecutor:**

| Factor | InterpreterPoolExecutor | ProcessPoolExecutor |
|--------|------------------------|---------------------|
| Startup cost | Lower (thread creation) | Higher (process creation) |
| Memory overhead | Lower (shared process memory) | Higher (full process copy) |
| Data sharing | Limited (must be shareable types) | Via pickle or shared_memory |
| Isolation | GIL-isolated, same address space | Full process isolation |
| Maturity | New in 3.14 — test thoroughly | Battle-tested |

**Decision:** Use `ProcessPoolExecutor` as the default for CPU-bound work. Evaluate `InterpreterPoolExecutor` for workloads with frequent short-lived CPU tasks where process startup overhead is measurable.

---

## Resilience Patterns

### Layered Resilience Architecture

Resilience is not an LLM-specific concern (doc 30). Every external call — market data APIs, broker APIs, payment providers, databases, Redis, third-party services — needs protection. The standard pattern layers defences from outside in:

```
Request
  → Circuit Breaker (prevent calls to known-failed services)
    → Retry with Backoff (handle transient failures)
      → Bulkhead / Semaphore (limit concurrent access)
        → Timeout (bound wall-clock time)
          → Actual Call
```

This ordering ensures:
- Retries don't hammer a service that the circuit breaker knows is down
- The bulkhead prevents one slow dependency from consuming all connections
- The timeout prevents any single call from blocking indefinitely

### Circuit Breaker: pybreaker

**Standard:** `pybreaker` for synchronous code, `aiobreaker` for async code.

```python
import aiobreaker

market_data_breaker = aiobreaker.CircuitBreaker(
    fail_max=5,               # Open after 5 failures
    timeout_duration=30,      # Stay open for 30 seconds
    exclude=[ValueError],     # Don't count validation errors
)

@market_data_breaker
async def fetch_price(symbol: str) -> Price:
    async with asyncio.timeout(07):
        return await market_client.get_price(symbol)
```

**Configuration per dependency type:**

| Dependency | fail_max | timeout_duration | Rationale |
|-----------|----------|------------------|-----------|
| Market data API | 5 | 30s | Fast recovery needed for trading |
| LLM provider | 3 | 60s | Slower recovery acceptable |
| Payment/broker API | 3 | 60s | Must not retry aggressively |
| Internal microservice | 5 | 15s | Should recover quickly |
| Database | 3 | 10s | If DB is down, most operations fail anyway |

**States:**
- **Closed** (normal): Calls pass through. Failures counted. Opens when `fail_max` exceeded.
- **Open** (tripped): All calls fail immediately with `CircuitBreakerError`. No load on failing service.
- **Half-Open** (testing): After `timeout_duration`, one test call is allowed. Success closes the breaker; failure reopens it.

**Circuit breaker for Redis state sharing** (distributed systems): Configure `pybreaker` with a Redis-backed state storage so all instances of a service share breaker state. When one instance detects failure, all instances stop calling.

### Retry with Backoff: tenacity

**Standard:** `tenacity` for all retry logic. No hand-rolled retry loops.

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def place_order(order: Order) -> OrderResult:
    """Place order with broker API. Retries on transient failures."""
    async with asyncio.timeout(34):
        return await broker_client.submit(order)
```

`tenacity` auto-detects async functions — no separate decorator needed.

**Retry policies by operation type:**

| Operation | Max Attempts | Backoff | Retry On |
|-----------|-------------|---------|----------|
| Market data fetch | 3 | Exponential 1–10s | `ConnectionError`, `TimeoutError` |
| Order placement | 2 | Exponential 2–15s | `ConnectionError` only (never retry on business errors) |
| LLM call | 3 | Exponential 1–30s | `RateLimitError`, `ServerError`, `TimeoutError` |
| Database query | 2 | Fixed 1s | `OperationalError` (connection lost) |
| Email/notification | 3 | Exponential 5–60s | All transient errors |

**Rules:**
- **Always set `stop`.** Retries without a stop condition run forever.
- **Always set `retry` to specific exception types.** Never retry on `Exception` — that retries validation errors, auth failures, and business logic errors.
- **Never retry non-idempotent operations** unless the operation uses idempotency keys (per P6 in doc 02).
- **Log before each retry** with `before_sleep_log` — silent retries are invisible retries.

### Composing the Full Stack

Combine all layers for a production external call:

```python
import asyncio
import aiobreaker
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Layer 1: Circuit breaker (outermost)
_price_breaker = aiobreaker.CircuitBreaker(fail_max=5, timeout_duration=30)

# Layer 2: Semaphore / bulkhead
_price_semaphore = asyncio.Semaphore(24)

@_price_breaker
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    reraise=True,
)
async def get_price(symbol: str) -> Price:
    """Fetch price with full resilience stack."""
    # Layer 3: Bulkhead
    async with _price_semaphore:
        # Layer 4: Timeout
        async with asyncio.timeout(07):
            return await market_client.get_price(symbol)
```

The circuit breaker wraps the retry decorator. When the breaker is open, `tenacity` never fires — the call fails immediately. When the breaker is closed, transient failures trigger retries with backoff. The semaphore limits concurrent calls regardless of retry state. The timeout bounds each individual attempt.

---

## Context Propagation for Observability

### The Problem

Doc 08 standardizes structlog with `X-Request-ID` propagation — but only within the HTTP request thread. When work fans out to threads, processes, or background tasks, context is lost. A `request_id` that disappears when you call `asyncio.to_thread()` means you can't trace a request through your system. That's unacceptable.

### contextvars: The Foundation

Python's `contextvars` module is the standard mechanism for propagating state across async boundaries. structlog already uses it (via `structlog.contextvars`). The key behaviors:

| Boundary | Context Propagation | Action Required |
|----------|-------------------|-----------------|
| `asyncio.create_task()` | **Automatic** — copies context at creation | None |
| `asyncio.TaskGroup` | **Automatic** — each task gets parent context | None |
| `ThreadPoolExecutor.submit()` | **Not propagated** | Wrap executor (see below) |
| `ProcessPoolExecutor.submit()` | **Not propagated** | Serialize and inject (see below) |
| Taskiq background tasks | **Not propagated** | Pass as task arguments |

### TracedThreadPoolExecutor

All `ThreadPoolExecutor` usage must use this wrapper to propagate context:

```python
import contextvars
from concurrent.futures import ThreadPoolExecutor

class TracedThreadPoolExecutor(ThreadPoolExecutor):
    """ThreadPoolExecutor that propagates contextvars to worker threads."""

    def submit(self, fn, /, *args, **kwargs):
        ctx = contextvars.copy_context()
        return super().submit(ctx.run, fn, *args, **kwargs)
```

Use `TracedThreadPoolExecutor` everywhere you would use `ThreadPoolExecutor`. This ensures `request_id`, `frontend`, structlog bindings, and OpenTelemetry spans all propagate to threads.

```python
# Module-level pool
_io_pool = TracedThreadPoolExecutor(max_workers=10)

async def read_large_file(path: str) -> str:
    """Read file in thread pool — context propagated automatically."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_io_pool, Path(path).read_text)
```

### Process Context Propagation

For `ProcessPoolExecutor`, context cannot be copied (processes don't share memory). Pass trace identifiers explicitly:

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

_cpu_pool = ProcessPoolExecutor(max_workers=4)

async def compute_risk(positions, request_id: str) -> RiskMetrics:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _cpu_pool,
        _compute_risk_with_context,
        positions,
        request_id,  # Pass context explicitly
    )

def _compute_risk_with_context(positions, request_id: str) -> RiskMetrics:
    """Runs in child process — rebind logging context."""
    import structlog
    structlog.contextvars.bind_contextvars(request_id=request_id, source="compute")
    logger = structlog.get_logger()
    logger.info("Starting risk computation")
    # ... computation ...
```

### OpenTelemetry Span Propagation

When adding OpenTelemetry (see doc 08 production stack), propagate trace context across process boundaries:

```python
from opentelemetry.context.contextvars_context import ContextVarsRuntimeContext
from opentelemetry.trace.propagation import TraceContextTextMapPropagator

propagator = TraceContextTextMapPropagator()

# Inject: serialize current span context to dict
carrier = {}
propagator.inject(carrier)
# Pass carrier to child process as argument

# Extract: in child process, restore span context
ctx = propagator.extract(carrier)
with tracer.start_as_current_span("child_operation", context=ctx):
    # ... work with restored trace context ...
```

### Taskiq Task Context

For background tasks (doc 15), pass `request_id` and `correlation_id` as task arguments:

```python
await tasks["process_signal"].kiq(
    signal_data=data,
    request_id=request.state.request_id,
    correlation_id=str(uuid4()),
)

async def process_signal(signal_data: dict, request_id: str, correlation_id: str):
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        correlation_id=correlation_id,
        source="tasks",
    )
    # All subsequent logs include request_id and correlation_id
```

---

## Graceful Shutdown

### The Problem

A kill signal during active request processing causes partial writes, orphaned connections, lost in-flight tasks, and corrupted state. Trading systems cannot tolerate this.

### Shutdown Sequence

All services follow this sequence on SIGTERM/SIGINT:

```
1. Mark service unhealthy          (readiness probe returns 503)
2. Wait for propagation            (sleep 2-3 seconds)
3. Stop accepting new connections
4. Drain in-flight requests         (with timeout)
5. Flush pending logs/metrics
6. Close connection pools           (database, Redis, HTTP clients)
7. Cancel remaining async tasks
8. Exit cleanly
```

### FastAPI Implementation

```python
import asyncio
import signal
from contextlib import asynccontextmanager

_shutting_down = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — startup and shutdown."""
    # Startup
    logger.info("Starting application")
    await init_database_pool()
    await init_redis_pool()
    
    yield  # Application runs here
    
    # Shutdown
    global _shutting_down
    _shutting_down = True
    logger.info("Shutdown initiated — draining requests")
    
    await asyncio.sleep(3)  # Let load balancer remove us
    
    # Close pools
    await close_database_pool()
    await close_redis_pool()
    await close_http_clients()
    
    logger.info("Shutdown complete")

app = FastAPI(lifespan=lifespan)

@app.get("/health/ready")
async def readiness():
    if _shutting_down:
        return JSONResponse({"status": "shutting_down"}, status_code=503)
    # ... normal readiness checks ...
```

### Uvicorn Configuration

```bash
uvicorn modules.backend.main:app \
    --loop uvloop \
    --timeout-graceful-shutdown 30 \
    --host 0.0.0.0 \
    --port 8000
```

### Docker / Container Considerations

- Use `tini` or `dumb-init` as PID 1 — Python does not handle signals correctly as PID 1 in containers
- Set `STOPSIGNAL SIGTERM` in Dockerfile
- Set Kubernetes `terminationGracePeriodSeconds` to at least `timeout-graceful-shutdown + 5`

```dockerfile
FROM python:3.14-slim
RUN pip install tini
ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "modules.backend.main:app", "--loop", "uvloop"]
```

---

## Platform-Specific Guidance

### macOS vs Linux

| Concern | macOS | Linux | Action |
|---------|-------|-------|--------|
| Multiprocessing default (3.14) | `spawn` | `forkserver` | Do not override — both are safe |
| Event loop backend | kqueue | epoll | Both O(1) — no action needed |
| File descriptor limit | **256** (default) | 1,024 (default) | **Increase on macOS** (see below) |
| `fork()` safety | Unsafe (system frameworks) | Safer but problematic with threads | Never use `fork` start method explicitly |
| `/dev/shm` (shared memory tmpfs) | Not available | Available | Use `SharedMemory` API (works on both) |
| Docker runtime | Linux VM (Virtualization.framework) | Native kernel | Expect 3x I/O overhead on macOS Docker |

### macOS File Descriptor Limit

This **will** bite you. A FastAPI service with 50 concurrent connections, a database pool of 20, Redis connections, and HTTP client pools easily exceeds 256 file descriptors.

Add to your shell profile (`~/.zshrc` or `~/.bashrc`):
```bash
ulimit -n 10240
```

For persistent system-wide change on macOS:
```bash
sudo launchctl limit maxfiles 10240 524288
```

### Development on macOS, Production on Linux

This is the expected workflow. Key differences to account for:

- **Test multiprocessing behavior on Linux** before deployment — `spawn` (macOS) has different pickle requirements than `forkserver` (Linux)
- **Docker on macOS** uses VirtioFS for bind mounts — roughly 3x slower than native. Use named volumes for databases and log-heavy workloads during development
- **OrbStack** is recommended over Docker Desktop for macOS development — 75–95% native filesystem performance
- **Always run performance benchmarks on Linux** — macOS VM overhead makes benchmark numbers unreliable

---

## Profiling Concurrent Code

### Standard Tools

| Tool | Use Case | Overhead | Install |
|------|----------|----------|---------|
| `py-spy` | Production thread debugging, deadlock detection | Near-zero (sampling) | `pip install py-spy` |
| `yappi` | Deterministic async/thread profiling | Moderate | `pip install yappi` |
| `Scalene` | Memory + CPU profiling with line-level detail | Low–moderate | `pip install scalene` |
| `python -m asyncio pstree <PID>` | Live async task tree inspection | None | Built-in (3.14) |

### py-spy for Production Debugging

Attach to a running process without restart or instrumentation:

```bash
# Dump all thread stacks (diagnose deadlocks, stuck requests)
py-spy dump --pid <PID>

# Record flame graph for 30 seconds
py-spy record -o profile.svg --pid <PID> --duration 30

# Top-like live view of where time is spent
py-spy top --pid <PID>
```

**This is your first tool** when a production service is slow or stuck. Zero setup, zero code changes, near-zero overhead.

### yappi for Async Profiling

Statistical profilers (py-spy, cProfile) cannot correctly attribute time across `await` boundaries — they see coroutine suspension as idle time. yappi tracks wall-clock and CPU time per coroutine correctly.

```python
import yappi

yappi.set_clock_type("wall")  # Wall clock for async code
yappi.start()

# ... run your async workload ...

yappi.stop()
stats = yappi.get_func_stats()
stats.sort("totaltime", "desc")
stats.print_all(columns={
    0: ("name", 80),
    1: ("ncall", 10),
    2: ("tsub", 8),
    3: ("ttot", 8),
})
```

### asyncio Introspection CLI (3.14+)

Inspect all running tasks in a live process:

```bash
# List all tasks with their coroutine and state
python -m asyncio ps <PID>

# Show task tree (parent/child relationships)
python -m asyncio pstree <PID>
```

**Use this first** when debugging stuck async services. It shows exactly which coroutines are awaiting what — no instrumentation required.

---

## Configuration

All concurrency and resilience settings are centralized in YAML configuration per doc 04:

```yaml
# config/settings/concurrency.yaml

concurrency:
  uvloop_enabled: true
  eager_task_factory: true
  
  thread_pool:
    max_workers: 10          # TracedThreadPoolExecutor
  
  process_pool:
    max_workers: 4           # ProcessPoolExecutor for CPU work
    
  semaphores:
    market_data: 20
    llm_provider: 5
    database: 50
    redis: 100

resilience:
  circuit_breaker:
    market_data:
      fail_max: 5
      timeout_duration: 30
    llm_provider:
      fail_max: 3
      timeout_duration: 60
    broker_api:
      fail_max: 3
      timeout_duration: 60
      
  retry:
    market_data:
      max_attempts: 3
      backoff_multiplier: 1
      backoff_max: 10
    order_placement:
      max_attempts: 2
      backoff_multiplier: 2
      backoff_max: 15

  timeouts:
    database_query: 10
    internal_api: 10
    external_api: 30
    llm_call: 120
    file_operation: 30
    batch_processing: 120

shutdown:
  graceful_timeout: 30       # Seconds to drain requests
  propagation_delay: 3       # Seconds to wait for LB to remove us
```

---

## Testing Concurrent Code

### Unit Testing Async Code

All async tests use `pytest-asyncio`:

```python
import pytest

@pytest.mark.asyncio
async def test_parallel_signal_fetch():
    """Verify parallel fetch returns all results."""
    signals = await get_trading_signals(["AAPL", "GOOG", "MSFT"])
    assert len(signals) == 3
```

### Testing Resilience Patterns

Test circuit breaker and retry behavior explicitly:

```python
import pytest
from unittest.mock import AsyncMock, patch
from aiobreaker import CircuitBreakerError

@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures():
    """Circuit breaker opens after fail_max consecutive failures."""
    client = AsyncMock(side_effect=ConnectionError("down"))
    
    with pytest.raises(ConnectionError):
        for _ in range(5):
            await fetch_price_with_breaker("AAPL", client=client)
    
    # Next call should fail immediately with CircuitBreakerError
    with pytest.raises(CircuitBreakerError):
        await fetch_price_with_breaker("AAPL", client=client)

@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    """Transient failure followed by success should return result."""
    client = AsyncMock(side_effect=[ConnectionError("blip"), Price(100.0)])
    
    result = await fetch_price_with_retry("AAPL", client=client)
    
    assert result.value == 100.0
    assert client.call_count == 2
```

### Testing Timeouts

```python
@pytest.mark.asyncio
async def test_timeout_raises_on_slow_response():
    """Operations exceeding timeout raise TimeoutError."""
    async def slow_response():
        await asyncio.sleep(60)
    
    with pytest.raises(asyncio.TimeoutError):
        async with asyncio.timeout(0.1):
            await slow_response()
```

### Testing Context Propagation

```python
import structlog

@pytest.mark.asyncio
async def test_context_propagates_to_task_group():
    """Verify structlog context propagates into TaskGroup tasks."""
    structlog.contextvars.bind_contextvars(request_id="test-123")
    
    captured_ids = []
    
    async def capture_context():
        ctx = structlog.contextvars.get_contextvars()
        captured_ids.append(ctx.get("request_id"))
    
    async with asyncio.TaskGroup() as tg:
        tg.create_task(capture_context())
        tg.create_task(capture_context())
    
    assert captured_ids == ["test-123", "test-123"]
```

---

## Adoption Checklist

When adopting this standard:

- [ ] Upgrade to Python 3.14 (update `pyproject.toml`, deployment configs in docs 17/22)
- [ ] Install and configure `uvloop` as default event loop
- [ ] Install `tenacity` and `aiobreaker` (or `pybreaker`)
- [ ] Replace all `ThreadPoolExecutor` usage with `TracedThreadPoolExecutor`
- [ ] Add concurrency configuration to `config/settings/concurrency.yaml`
- [ ] Implement graceful shutdown in FastAPI `lifespan`
- [ ] Set `ulimit -n 10240` in macOS development environments
- [ ] Add `tini` or `dumb-init` to Docker images
- [ ] Configure Uvicorn with `--loop uvloop --timeout-graceful-shutdown 30`
- [ ] Install `py-spy` in production environments for live debugging
- [ ] Add semaphores to all external service call sites
- [ ] Add circuit breakers to all external dependency clients
- [ ] Add retry decorators to all transient-failure-prone calls
- [ ] Verify context propagation in integration tests
- [ ] Update doc 08 health checks to include circuit breaker state reporting

### For Trading-Specific Workloads

- [ ] Configure `ProcessPoolExecutor` for technical indicator computation
- [ ] Implement shared memory for large price/OHLCV arrays
- [ ] Set aggressive timeouts for market data (5–10s max)
- [ ] Set circuit breaker `timeout_duration` to 15–30s for market data (fast recovery)
- [ ] Verify graceful shutdown drains open orders/positions cleanly
- [ ] Add profiling harness (`yappi`) to staging environment for async hot-path analysis

---

## Dependencies on Other Documents

| Document | Relationship |
|----------|-------------|
| 02-core-principles.md | P5 (Fail Fast), P6 (Idempotency), O2 (Graceful Degradation), O3 (Bounded Resources) — this doc implements all four |
| 04-core-backend-architecture.md | Extends async patterns section; supersedes TaskGroup and timeout guidance |
| 21-opt-event-architecture.md | Resilience patterns apply to event consumers and publishers |
| 30-ai-llm-integration.md | Circuit breaker and retry patterns extracted to this doc as cross-cutting; doc 30 references this doc |
| 08-core-observability.md | Context propagation patterns extend structlog guidance; profiling tools complement production monitoring |
| 15-core-background-tasks.md | Context propagation applies to Taskiq workers |
| 17-core-deployment-bare-metal.md | Python 3.14 upgrade, uvloop, tini, graceful shutdown |
| 18-core-deployment-azure.md | Python 3.14 upgrade, uvloop, graceful shutdown, App Service configuration |
| 31-ai-agentic-architecture.md | Timeout and resilience patterns apply to agent orchestration |
| 32-ai-agentic-pydanticai.md | Context propagation applies to agent task execution |
