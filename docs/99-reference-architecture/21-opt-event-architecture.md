# 21 — Event Architecture

*Version: 2.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 2.0.0 (2026-03-01): Added FastStream as standard event framework. Added consumer resilience patterns (circuit breaker, retry, timeout — references 16-core-concurrency-and-resilience.md). Added concrete dead letter queue implementation. Added consumer lag monitoring with Prometheus metrics. Added backpressure patterns. Added trace context propagation in event envelope. Added Faust deprecation notice. Added broker selection guide for upgrade path. Integrated with 08-core-observability.md resilience event logging.
- 1.0.0 (2025-01-27): Initial generic event architecture standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project needs:
- Asynchronous event processing
- Real-time updates to clients
- Decoupled service communication
- Event-driven workflows
- Streaming data pipelines (market data, telemetry, sensor feeds)

For simple request-response applications, this module is not required.

---

## Context

Synchronous request-response works for most interactions, but some operations shouldn't block the caller: sending notifications after an order is placed, updating search indexes after content changes, broadcasting state changes to multiple consumers, pushing agent responses to connected clients, or processing streaming market data. This module exists for projects that need to decouple producers from consumers.

Redis Streams remains the **default broker** because it provides reliable message delivery with consumer groups, is already present in most deployments (for caching and task queues via 19-background-tasks), and handles thousands of events per second — sufficient for the vast majority of projects. The upgrade path to NATS JetStream or Apache Kafka is defined with concrete guidance for when each becomes necessary.

Version 2.0.0 adds **FastStream** as the standard framework for event producers and consumers. The 1.0.0 standard defined raw Redis Streams patterns — `XADD`, `XREADGROUP`, `XACK` — which work but leave each project to reinvent error handling, serialization, middleware, dependency injection, and testing. FastStream wraps the underlying broker with a FastAPI-style developer experience: Pydantic message validation, dependency injection, middleware chains, and structured error handling. Critically, it supports multiple brokers through a unified API, so the upgrade path from Redis Streams to NATS or Kafka is a configuration change rather than a rewrite.

This version also addresses three gaps that matter for production systems: **consumer resilience** (what happens when a consumer's downstream dependency fails), **backpressure** (what happens when producers outpace consumers), and **observability** (how to detect and alert on consumer lag before it becomes a business problem). The resilience patterns follow **16-core-concurrency-and-resilience.md** — the same circuit breaker → retry → timeout layering that applies to HTTP calls applies to event consumers.

The transactional outbox pattern is unchanged — it remains the correct solution for the dual-write problem. This module provides the communication backbone for inter-module events (05), real-time client updates (07, 29), and is a required dependency for the agentic architecture (31).

---

## Event-Driven Design

### When to Use Events

Events are appropriate for:
- Decoupling services that don't need synchronous responses
- Broadcasting state changes to multiple consumers
- Triggering background processing
- Real-time updates to clients (via 27-opt-multi-channel-gateway.md)
- Audit trail requirements
- Streaming data processing (market data, telemetry)
- Agent lifecycle notifications (31-ai-agentic-architecture.md)

Events are not appropriate for:
- Operations requiring immediate response
- Operations requiring transaction guarantees across services
- Simple request-response patterns

### Event vs Command

**Events** describe something that happened (past tense):
- OrderPlaced
- UserCreated
- PaymentProcessed
- SignalGenerated
- AgentTaskCompleted

**Commands** request an action (imperative):
- PlaceOrder
- CreateUser
- ProcessPayment

This architecture uses events for communication between services. Commands are internal to services.

---

## Event Framework

### Standard: FastStream

All event producers and consumers use **FastStream** as the framework layer.

Rationale:
- **Unified API across brokers** — same code works with Redis Streams, Kafka, NATS, and RabbitMQ. Broker swap is configuration, not rewrite.
- **Pydantic message validation** — events are typed, validated on publish and consume. Malformed events fail fast.
- **Dependency injection** — same pattern as FastAPI. Services, database sessions, and configuration injected into handlers.
- **Middleware chain** — cross-cutting concerns (logging, tracing, error handling, metrics) applied uniformly.
- **Testable without broker** — call handler functions directly in unit tests, use `TestBroker` for integration tests.
- **AsyncIO-native** — matches FastAPI and the concurrency model in 16-core-concurrency-and-resilience.md.
- **Approaching 1.0** — v0.5.34 as of early 2026, actively maintained, production-adopted.

**Installation:**
```
pip install "faststream[redis]"
```

Replace `redis` with `kafka`, `nats`, or `rabbit` when upgrading brokers.

### Deprecated: Faust

Faust (originally Robinhood's stream processing library) is **officially deprecated** and unmaintained. Do not use it for new projects. Existing Faust consumers should migrate to FastStream or, for complex stream processing requiring windowing and stateful aggregation, Apache Flink.

---

## Messaging Infrastructure

### Default Broker: Redis Streams

Redis Streams handles event delivery for moderate scale (thousands of events per second).

Rationale:
- Already deployed for caching and task queues (doc 23)
- Consumer groups for reliable delivery
- Message acknowledgment
- Replay capability
- No additional infrastructure

### FastStream with Redis Streams

```python
from faststream import FastStream
from faststream.redis import RedisBroker, RedisMessage
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

# Broker setup
broker = RedisBroker("redis://localhost:6379")
app = FastStream(broker)

# Event schema (Pydantic model)
class OrderPlaced(BaseModel):
    event_id: str
    event_type: str = "orders.order.placed"
    event_version: int = 1
    timestamp: str
    source: str
    correlation_id: str
    payload: dict

# Publisher
publisher = broker.publisher("orders:order-placed")

async def publish_order_placed(order: dict, correlation_id: str):
    event = OrderPlaced(
        event_id=str(uuid4()),
        timestamp=utc_now().isoformat(),
        source="order-service",
        correlation_id=correlation_id,
        payload=order,
    )
    await publisher.publish(event)

# Consumer
@broker.subscriber(
    "orders:order-placed",
    group="notification-service",
)
async def handle_order_placed(event: OrderPlaced):
    """Process order placed event — send notification."""
    structlog.contextvars.bind_contextvars(
        correlation_id=event.correlation_id,
        event_type=event.event_type,
        source="events",
    )
    logger.info("Processing order placed event", order_id=event.payload.get("order_id"))
    
    await notification_service.send(
        user_id=event.payload["user_id"],
        message=f"Order {event.payload['order_id']} confirmed",
    )
```

### FastStream Middleware

Apply cross-cutting concerns to all consumers:

```python
from faststream import BaseMiddleware

class ObservabilityMiddleware(BaseMiddleware):
    """Bind logging context and emit metrics for every consumed event."""

    async def on_consume(self, msg):
        """Called before the handler runs."""
        structlog.contextvars.bind_contextvars(
            event_id=msg.get("event_id"),
            correlation_id=msg.get("correlation_id"),
            event_type=msg.get("event_type"),
            source="events",
        )
        self._start_time = time.monotonic()
        return await super().on_consume(msg)

    async def after_consume(self, err):
        """Called after the handler completes (success or failure)."""
        duration_ms = (time.monotonic() - self._start_time) * 1000
        if err:
            logger.error(
                "Event processing failed",
                duration_ms=duration_ms,
                error=str(err),
            )
            event_processing_errors.labels(event_type=...).inc()
        else:
            logger.info("Event processed", duration_ms=duration_ms)
            event_processing_duration.labels(event_type=...).observe(duration_ms / 1000)
        
        structlog.contextvars.unbind_contextvars(
            "event_id", "correlation_id", "event_type",
        )
        return await super().after_consume(err)

broker = RedisBroker("redis://localhost:6379", middlewares=[ObservabilityMiddleware])
```

### FastStream Testing

Unit tests call handler functions directly — no broker required:

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_order_placed_sends_notification():
    """Handler sends notification for valid order event."""
    notification_service = AsyncMock()
    
    event = OrderPlaced(
        event_id="test-1",
        timestamp="2026-03-01T12:00:00Z",
        source="test",
        correlation_id="corr-1",
        payload={"order_id": "ord-123", "user_id": "user-456"},
    )
    
    await handle_order_placed(event)
    
    notification_service.send.assert_called_once()
```

Integration tests use `TestBroker` to verify publish/consume flow without Redis:

```python
from faststream.redis import TestRedisBroker

@pytest.mark.asyncio
async def test_order_event_flow():
    """Full publish → consume flow works end to end."""
    async with TestRedisBroker(broker) as test_broker:
        await test_broker.publish(
            OrderPlaced(
                event_id="test-1",
                timestamp="2026-03-01T12:00:00Z",
                source="test",
                correlation_id="corr-1",
                payload={"order_id": "ord-123", "user_id": "user-456"},
            ),
            "orders:order-placed",
        )
        
        # Verify handler was called
        handle_order_placed.mock.assert_called_once()
```

---

### Channel Naming

Format: `{domain}:{event-type}`

Examples:
- `orders:order-placed`
- `users:user-created`
- `payments:payment-processed`
- `signals:signal-generated`
- `agents:task-completed`

### Consumer Groups

Each consuming service creates a consumer group. Multiple instances of the same service share the consumer group (competing consumers pattern).

Consumer group naming: `{service-name}-{purpose}`

FastStream handles consumer group creation and management automatically when the `group` parameter is specified on `@broker.subscriber()`.

### Redis Streams Failure Modes

Understand these operational risks:

| Failure Mode | Impact | Mitigation |
|--------------|--------|------------|
| AOF sync gap | Up to 1 second data loss | Use `appendfsync always` for critical streams |
| Consumer crash | Messages stuck in Pending Entries List | Implement periodic `XAUTOCLAIM` (see Stale Message Recovery) |
| Memory exhaustion | Stream growth consumes RAM | Use `MAXLEN` to cap stream size |
| Slow consumer | Producer outpaces consumer, growing lag | Backpressure patterns (see Backpressure section) |

**Stale message recovery:**
```python
# Reclaim messages from crashed consumers (run periodically)
await redis.xautoclaim(
    stream_name,
    group_name,
    consumer_name,
    min_idle_time=300000,  # 5 minutes idle
    count=100
)
```

Schedule this as a Taskiq periodic task (doc 23) running every 5 minutes for each consumer group.

### Broker Selection Guide

Redis Streams is the default. When requirements exceed its capabilities, migrate using FastStream's broker abstraction.

| Requirement | Broker | Rationale |
|-------------|--------|-----------|
| Default (< 10K events/sec) | **Redis Streams** | Already deployed, no extra infrastructure |
| Sub-millisecond latency | **NATS JetStream** | Built for low-latency messaging |
| Multi-region distribution | **NATS JetStream** | Native multi-region clustering |
| Exactly-once semantics | **Apache Kafka** | Transactional producers, idempotent consumers |
| Unbounded replay / audit | **Apache Kafka** | Persistent log with configurable retention |
| > 100K events/sec sustained | **Apache Kafka** | Designed for sustained high-throughput |
| Complex routing / fanout | **RabbitMQ** | Exchange types, binding keys, flexible topology |
| Lightweight pub/sub only | **NATS Core** | Ultra-low overhead, no persistence needed |

**Migration path with FastStream:**

```python
# Before: Redis Streams
from faststream.redis import RedisBroker
broker = RedisBroker("redis://localhost:6379")

# After: NATS JetStream (change import and connection string only)
from faststream.nats import NatsBroker
broker = NatsBroker("nats://localhost:4222")

# After: Kafka (change import and connection string only)
from faststream.kafka import KafkaBroker
broker = KafkaBroker("localhost:9092")
```

Handler code, middleware, and tests remain identical. Pydantic schemas remain identical. Only the broker import and connection change.

**Do not migrate brokers speculatively.** Measure first. Redis Streams handles the majority of workloads. Migrate only when you have concrete evidence that Redis Streams is the bottleneck, and benchmark the alternative before committing.

---

## Consumer Resilience

Event consumers face the same failure modes as HTTP handlers: the downstream service they call can be slow, unavailable, or returning errors. Without resilience, a failing downstream dependency causes unconsumed messages to pile up, consumer lag to grow, and the entire event pipeline to stall.

All consumer resilience follows the patterns in **16-core-concurrency-and-resilience.md**. All resilience events are logged per the contract in **08-core-observability.md**.

### Resilience Stack for Consumers

The same layered approach applies:

```
Event received
  → Circuit Breaker (skip processing if downstream is known-failed)
    → Retry with Backoff (handle transient failures)
      → Timeout (bound processing time)
        → Handler Logic (actual business processing)
          → Acknowledge (only after successful processing)
```

### Implementation

```python
import asyncio
import aiobreaker
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Circuit breaker for the dependency this consumer calls
_notification_breaker = aiobreaker.CircuitBreaker(
    fail_max=5,
    timeout_duration=30,
    listeners=[ResilienceLogger("notification_service")],  # From doc 30
)

@broker.subscriber("orders:order-placed", group="notification-service")
async def handle_order_placed(event: OrderPlaced):
    """Process order event with full resilience stack."""
    structlog.contextvars.bind_contextvars(
        correlation_id=event.correlation_id,
        event_type=event.event_type,
        source="events",
    )
    
    try:
        await _process_with_resilience(event)
    except aiobreaker.CircuitBreakerError:
        logger.error(
            "Circuit breaker open — cannot process event",
            resilience_event="circuit_breaker_rejected",
            dependency="notification_service",
        )
        # NACK or let FastStream retry later
        raise
    except Exception as e:
        logger.error("Event processing failed after retries", error=str(e))
        raise  # FastStream handles DLQ routing

@_notification_breaker
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    reraise=True,
)
async def _process_with_resilience(event: OrderPlaced):
    """Resilient processing — circuit breaker wraps retry wraps timeout."""
    async with asyncio.timeout(34):
        await notification_service.send(
            user_id=event.payload["user_id"],
            message=f"Order {event.payload['order_id']} confirmed",
        )
```

### When the Circuit Breaker Opens

When a consumer's circuit breaker opens, the consumer cannot process events. The standard response depends on the event's criticality:

| Event Criticality | Breaker Open Behavior |
|-------------------|-----------------------|
| **Critical** (order placed, payment processed) | NACK the message — it stays in the Pending Entries List and will be retried when the breaker closes. Alert immediately. |
| **Standard** (notification, analytics) | Move to dead letter queue for later replay. Alert on warning level. |
| **Best-effort** (cache invalidation, enrichment) | Drop and acknowledge. Log the skip. No alert. |

Configure criticality per consumer in `config/settings/events.yaml`:

```yaml
consumers:
  notification-service:
    stream: "orders:order-placed"
    criticality: standard          # critical | standard | best_effort
    circuit_breaker:
      fail_max: 5
      timeout_duration: 30
    retry:
      max_attempts: 3
      backoff_multiplier: 1
      backoff_max: 10
    processing_timeout: 30
```

---

## Backpressure

### The Problem

When producers publish events faster than consumers can process them, one of three things happens: the broker's memory grows unboundedly, events are silently dropped, or the system applies backpressure. Only the third is acceptable.

For trading systems, this is not theoretical — a burst of market data events during high volatility will outpace any consumer that makes downstream API calls.

### Strategies

| Strategy | When to Use | Trade-Off |
|----------|-------------|-----------|
| **MAXLEN stream cap** | Default — prevent memory exhaustion | Old events trimmed, potential data loss |
| **Consumer scaling** | Production — scale workers horizontally | Requires infrastructure support |
| **Skip-to-latest** | Time-sensitive data (market prices) | Missed intermediate events |
| **Producer rate limiting** | Controlled environments | Slows the producer, adds latency |

### MAXLEN: Capped Streams (Default)

All Redis Streams must have a `MAXLEN` cap. Unbounded streams are forbidden (per P5 — O3 Bounded Resource Usage in doc 02).

```python
# Publisher with MAXLEN cap
await redis.xadd(
    "signals:price-update",
    fields=event.model_dump(),
    maxlen=100_000,      # Keep last 100K messages
    approximate=True,    # ~ prefix — Redis trims lazily for performance
)
```

**MAXLEN sizing guidance:**

| Stream Type | MAXLEN | Rationale |
|-------------|--------|-----------|
| High-frequency (price ticks, telemetry) | 10,000–50,000 | Recent data only, consumers process in near-real-time |
| Standard (order events, notifications) | 100,000 | Buffer for consumer downtime |
| Audit / compliance | No MAXLEN (use Kafka) | Audit requires unbounded retention — use Kafka, not Redis |

### Skip-to-Latest (Time-Sensitive Data)

For market data and other time-sensitive streams, a consumer that falls behind should skip to the latest event rather than processing a stale backlog:

```python
@broker.subscriber(
    "signals:price-update",
    group="signal-processor",
)
async def handle_price_update(event: PriceUpdate):
    """Process price update — skip stale data if behind."""
    event_age_ms = (utc_now() - datetime.fromisoformat(event.timestamp)).total_seconds() * 1000
    
    if event_age_ms > MAX_STALENESS_MS:
        logger.warning(
            "Skipping stale event",
            event_age_ms=event_age_ms,
            max_staleness_ms=MAX_STALENESS_MS,
        )
        consumer_events_skipped.labels(
            stream="signals:price-update",
            reason="stale",
        ).inc()
        return  # Acknowledge and move on
    
    await process_price_signal(event)
```

Configure staleness thresholds per stream:

```yaml
backpressure:
  max_staleness_ms:
    "signals:price-update": 5000     # 5 seconds — trading data
    "agents:task-completed": 60000   # 60 seconds — agent events
    "orders:order-placed": 0         # Never skip — critical
```

A threshold of `0` means never skip — all events must be processed regardless of age.

### Consumer Scaling

When consumer lag grows despite skip-to-latest and fast processing, scale consumers horizontally. FastStream with Redis Streams consumer groups handles this automatically — add more worker processes and they share the load.

```bash
# Scale from 1 to 4 consumer workers
python cli.py --service event-worker --workers 4
```

Monitor `consumer_lag_events` (see Monitoring section) and scale when lag exceeds threshold.

---

## Delivery Guarantees

### At-Least-Once Delivery

Default guarantee for all events. Consumers must be idempotent.

Implementation:
- Consumer acknowledges after processing
- Failed processing results in redelivery
- Idempotency key in event payload (`event_id`)

### Exactly-Once Processing (When Required)

For critical operations (order processing, payment handling):

1. Receive event
2. Check `event_id` against processed events table
3. If already processed, acknowledge and skip
4. Process within database transaction
5. Record `event_id` in same transaction
6. Acknowledge event

```python
async def handle_with_exactly_once(event: OrderPlaced):
    """Exactly-once processing via idempotency check."""
    async with db.transaction():
        # Check if already processed
        if await db.fetchval(
            "SELECT 1 FROM processed_events WHERE event_id = $1",
            event.event_id,
        ):
            logger.info("Event already processed, skipping", event_id=event.event_id)
            return
        
        # Process
        await process_order(event.payload)
        
        # Mark as processed (same transaction)
        await db.execute(
            "INSERT INTO processed_events (event_id, processed_at) VALUES ($1, NOW())",
            event.event_id,
        )
```

---

## Event Structure

### Envelope

All events use this envelope:

```json
{
  "event_id": "uuid",
  "event_type": "domain.entity.action",
  "event_version": 1,
  "timestamp": "2026-03-01T12:00:00Z",
  "source": "service-name",
  "correlation_id": "uuid",
  "trace_id": "hex-string-or-null",
  "payload": {}
}
```

### Field Definitions

| Field | Purpose |
|-------|---------|
| event_id | Unique identifier for this event instance. Used as idempotency key. |
| event_type | Dot-notation type (orders.order.placed) |
| event_version | Schema version for payload |
| timestamp | When event occurred (UTC ISO 8601) |
| source | Service that generated the event |
| correlation_id | Links related events across services. Maps to `X-Request-ID` from the originating HTTP request. |
| trace_id | OpenTelemetry trace ID for distributed trace correlation (see doc 30). Null if tracing disabled. |
| payload | Event-specific data |

### Trace Context in Events

When OpenTelemetry tracing is enabled (doc 30), include `trace_id` in the event envelope. This links the event to the distributed trace that produced it, enabling end-to-end visibility from HTTP request → event publish → consumer processing:

```python
from opentelemetry import trace

async def publish_with_trace(event_type: str, payload: dict, correlation_id: str):
    """Publish event with trace context."""
    span = trace.get_current_span()
    trace_id = None
    if span and span.is_recording():
        trace_id = format(span.get_span_context().trace_id, "032x")
    
    event = EventEnvelope(
        event_id=str(uuid4()),
        event_type=event_type,
        timestamp=utc_now().isoformat(),
        source=APP_NAME,
        correlation_id=correlation_id,
        trace_id=trace_id,
        payload=payload,
    )
    await publisher.publish(event)
```

On the consumer side, rebind the trace context:

```python
@broker.subscriber("orders:order-placed", group="notification-service")
async def handle_order_placed(event: OrderPlaced):
    structlog.contextvars.bind_contextvars(
        correlation_id=event.correlation_id,
        trace_id=event.trace_id,  # Link consumer logs to original trace
        event_type=event.event_type,
        source="events",
    )
    # All logs from this handler are now correlated with the original request
```

### Pydantic Event Schema

Define event schemas as Pydantic models. FastStream validates automatically on publish and consume.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4

class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    event_version: int = 1
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str
    correlation_id: str
    trace_id: str | None = None
    payload: dict

class OrderPlaced(EventEnvelope):
    event_type: str = "orders.order.placed"
    
class SignalGenerated(EventEnvelope):
    event_type: str = "signals.signal.generated"
```

### Versioning

Event schemas are versioned. Consumers must handle:
- Current version
- One previous version (during migration)

Breaking changes require new event type or major version increment.

---

## Transactional Outbox Pattern

### The Problem: Dual Write

When a service updates a database AND publishes an event, two systems can fail independently:

```python
# Failure scenario: Lost event
await db.commit()           # Success
await redis.publish(event)  # Fails (network issue)
# Result: Database updated but event never published
```

### The Solution: Transactional Outbox

Write the event to the **same database** as business data in a **single transaction**:

```sql
BEGIN TRANSACTION
  UPDATE orders SET status = 'confirmed' WHERE id = 123;
  INSERT INTO event_outbox (event_type, payload, created_at) 
    VALUES ('order.confirmed', '{"order_id": 123}', NOW());
COMMIT
```

A separate **relay process** reads the outbox and publishes to the event bus.

### When to Use

| Use Case | Need Outbox? |
|----------|--------------|
| Order placed, notify downstream | Yes |
| Critical state changes | Yes |
| Signal generated from computation | No (computation is the source of truth, replay from inputs) |
| Analytics events | No (eventual consistency OK) |
| Cache invalidation | No (idempotent, can retry) |

### Outbox Table Schema

```sql
CREATE TABLE event_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(255) NOT NULL,
    event_payload JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    published_at TIMESTAMP NULL,
    correlation_id UUID NULL,
    trace_id VARCHAR(32) NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_error TEXT NULL
);

CREATE INDEX idx_outbox_unpublished ON event_outbox (created_at) 
    WHERE published_at IS NULL;
```

### Relay Process

Scheduled task polls outbox and publishes via FastStream:

```python
from modules.backend.tasks.scheduled import SCHEDULED_TASKS

async def publish_outbox_events():
    """Relay unpublished outbox events to the event bus."""
    events = await db.fetch("""
        SELECT * FROM event_outbox 
        WHERE published_at IS NULL 
        AND attempts < 5
        ORDER BY created_at LIMIT 100
        FOR UPDATE SKIP LOCKED
    """)
    
    published = 0
    for event in events:
        try:
            await publisher.publish(
                EventEnvelope(
                    event_type=event["event_type"],
                    correlation_id=str(event["correlation_id"]),
                    trace_id=event["trace_id"],
                    payload=event["event_payload"],
                ),
                channel=f"events:{event['event_type']}",
            )
            await db.execute(
                "UPDATE event_outbox SET published_at = NOW() WHERE id = $1",
                event["id"],
            )
            published += 1
        except Exception as e:
            await db.execute(
                "UPDATE event_outbox SET attempts = attempts + 1, last_error = $2 WHERE id = $1",
                event["id"],
                str(e),
            )
            logger.error(
                "Failed to publish outbox event",
                event_id=str(event["id"]),
                event_type=event["event_type"],
                error=str(e),
                attempt=event["attempts"] + 1,
            )
    
    if published:
        logger.info("Outbox relay completed", published=published, total=len(events))

SCHEDULED_TASKS["publish_outbox_events"] = {
    "function": publish_outbox_events,
    "schedule": [{"cron": "* * * * *"}],  # Every minute
    "retry_on_error": False,
    "description": "Relay unpublished events from outbox to event bus",
}
```

---

## Dead Letter Queue

Events that fail after maximum retries must not be silently lost. They are moved to a dead letter stream for investigation and manual replay.

### DLQ Stream Naming

Format: `dlq:{original-stream}`

Examples:
- `dlq:orders:order-placed`
- `dlq:signals:signal-generated`

### Implementation

FastStream does not provide built-in DLQ support for Redis Streams. Implement at the handler level:

```python
MAX_PROCESSING_ATTEMPTS = 3

@broker.subscriber("orders:order-placed", group="notification-service")
async def handle_order_placed(event: OrderPlaced, msg: RedisMessage):
    """Process order event with DLQ on exhausted retries."""
    attempt = int(msg.headers.get("x-retry-count", "0"))
    
    try:
        await _process_with_resilience(event)
    except Exception as e:
        if attempt >= MAX_PROCESSING_ATTEMPTS - 1:
            # Exhausted retries — move to DLQ
            await move_to_dlq(
                stream="orders:order-placed",
                event=event,
                error=str(e),
                attempts=attempt + 1,
            )
            logger.error(
                "Event moved to dead letter queue",
                event_id=event.event_id,
                stream="orders:order-placed",
                attempts=attempt + 1,
                error=str(e),
            )
            dlq_events_total.labels(stream="orders:order-placed").inc()
            return  # Acknowledge — don't reprocess
        
        raise  # Let FastStream/Redis retry

async def move_to_dlq(stream: str, event: EventEnvelope, error: str, attempts: int):
    """Move a failed event to the dead letter stream."""
    await redis.xadd(
        f"dlq:{stream}",
        {
            "original_event": event.model_dump_json(),
            "error": error,
            "attempts": str(attempts),
            "failed_at": utc_now().isoformat(),
            "original_stream": stream,
        },
    )
```

### DLQ Monitoring and Replay

Monitor DLQ depth and alert when events accumulate:

```python
# Prometheus metric
dlq_events_total = Counter(
    "dlq_events_total",
    "Events moved to dead letter queue",
    ["stream"],
)

dlq_depth = Gauge(
    "dlq_depth",
    "Current number of events in dead letter queue",
    ["stream"],
)
```

**Alert when DLQ is non-empty:**
```yaml
- alert: DeadLetterQueueNonEmpty
  expr: dlq_depth > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Dead letter queue has {{ $value }} events for {{ $labels.stream }}"
```

**Manual replay:**
```python
async def replay_dlq(stream: str, count: int = 10):
    """Replay events from DLQ back to the original stream."""
    events = await redis.xrange(f"dlq:{stream}", count=count)
    
    for msg_id, fields in events:
        original_event = json.loads(fields["original_event"])
        await redis.xadd(stream, original_event)
        await redis.xdel(f"dlq:{stream}", msg_id)
        logger.info("Replayed DLQ event", original_stream=stream, msg_id=msg_id)
```

---

## Consumer Lag Monitoring

Consumer lag — the difference between the latest event in a stream and the last event a consumer group has processed — is the single most important metric for event-driven systems. Growing lag means consumers are falling behind. For trading data, lag directly equals signal staleness.

### Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `consumer_lag_events` | Gauge | `stream`, `group` | Number of unprocessed events |
| `consumer_lag_ms` | Gauge | `stream`, `group` | Estimated lag in milliseconds |
| `consumer_processing_rate` | Counter | `stream`, `group` | Events processed per second |
| `consumer_events_skipped` | Counter | `stream`, `reason` | Events skipped (stale, low priority) |
| `dlq_events_total` | Counter | `stream` | Events moved to DLQ |
| `dlq_depth` | Gauge | `stream` | Current DLQ size |

### Lag Collection

Collect consumer lag via a periodic Taskiq task:

```python
async def collect_consumer_lag():
    """Measure consumer lag for all configured consumer groups."""
    for stream_config in config["consumers"].values():
        stream = stream_config["stream"]
        group = stream_config["group"]
        
        # Get stream length
        stream_info = await redis.xinfo_stream(stream)
        stream_length = stream_info["length"]
        
        # Get pending count for the consumer group
        try:
            group_info = await redis.xinfo_groups(stream)
            for g in group_info:
                if g["name"] == group:
                    lag = g["lag"] if "lag" in g else g["pending"]
                    consumer_lag_events.labels(
                        stream=stream,
                        group=group,
                    ).set(lag)
                    break
        except Exception as e:
            logger.warning("Failed to collect consumer lag", stream=stream, error=str(e))

SCHEDULED_TASKS["collect_consumer_lag"] = {
    "function": collect_consumer_lag,
    "schedule": [{"cron": "* * * * *"}],  # Every minute
    "retry_on_error": False,
    "description": "Collect consumer lag metrics for monitoring",
}
```

### Alerting

```yaml
# Consumer falling behind — standard streams
- alert: ConsumerLagHigh
  expr: consumer_lag_events > 1000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Consumer {{ $labels.group }} has {{ $value }} events lag on {{ $labels.stream }}"

# Consumer falling behind — trading streams (tighter threshold)
- alert: TradingConsumerLagHigh
  expr: consumer_lag_events{stream=~"signals:.*|prices:.*"} > 100
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Trading consumer {{ $labels.group }} has {{ $value }} events lag"
```

---

## Real-Time Data Patterns (Optional)

### WebSocket Integration

For real-time client updates, see **27-opt-multi-channel-gateway.md** which provides the comprehensive WebSocket connection management, session routing, and multi-channel push. The patterns below apply when 29 is not adopted.

Basic WebSocket flow:

1. Client connects to WebSocket endpoint
2. Server authenticates via token
3. Client sends subscription messages
4. Server adds client to relevant pub/sub channels
5. Events broadcast to client in real-time
6. Client disconnection cleans up subscriptions

### Message Types

Outbound (server to client):
- `data` - Payload data
- `status` - Connection status, errors
- `ack` - Acknowledgment of client message

Inbound (client to server):
- `subscribe` - Add subscription
- `unsubscribe` - Remove subscription
- `ping` - Keepalive

### Heartbeat/Keepalive

| Parameter | Value |
|-----------|-------|
| Server ping interval | 30 seconds |
| Client pong timeout | 10 seconds |
| Missed pongs before disconnect | 2 |

### Reconnection

Clients implement reconnection with exponential backoff:
- Initial delay: 1 second
- Maximum delay: 30 seconds
- Jitter to prevent thundering herd

---

## Periodic Task Patterns

### Scheduled Tasks

Use task timeout to prevent overlap:

```python
@scheduler.cron("*/15 * * * *")
@broker.task(timeout=840)  # 14 min timeout, 1 min buffer
async def periodic_task():
    await process_data()
```

### Failure Tolerance

Non-critical scheduled tasks:
- Single attempt per schedule
- Failures logged but not retried
- Next scheduled run proceeds normally

---

## Audit Trail

### What to Audit

All events that represent:
- State changes to important entities
- User actions with business impact
- System decisions affecting users
- Security-relevant operations
- Agent autonomous decisions (doc 31)

### Audit Storage

Audit events stored in append-only table:
- Never deleted (retention policy applied separately)
- Never updated
- Indexed by entity, user, timestamp
- Includes `correlation_id` and `trace_id` for full trace correlation

---

## Configuration

All event architecture settings centralized in `config/settings/events.yaml`:

```yaml
broker:
  type: "redis"                     # redis | nats | kafka
  url: "${REDIS_URL}"
  
streams:
  default_maxlen: 100000            # Default MAXLEN for new streams
  overrides:
    "signals:price-update":
      maxlen: 10000                 # Low for high-frequency trading data
    "orders:order-placed":
      maxlen: 500000                # High for critical business events

consumers:
  notification-service:
    stream: "orders:order-placed"
    group: "notification-service"
    criticality: standard
    circuit_breaker:
      fail_max: 5
      timeout_duration: 30
    retry:
      max_attempts: 3
      backoff_multiplier: 1
      backoff_max: 10
    processing_timeout: 30
    
  signal-processor:
    stream: "signals:price-update"
    group: "signal-processor"
    criticality: best_effort        # Skip stale, never block
    processing_timeout: 5

backpressure:
  max_staleness_ms:
    "signals:price-update": 5000
    "agents:task-completed": 60000
    "orders:order-placed": 0        # Never skip
```

---

## Adoption Checklist

When adopting this module:

- [ ] Install FastStream: `pip install "faststream[redis]"`
- [ ] Define event types as Pydantic models
- [ ] Configure broker in `config/settings/events.yaml`
- [ ] Implement event publisher utility with trace context injection
- [ ] Implement consumers with `@broker.subscriber()` and resilience stack
- [ ] Set up `MAXLEN` caps on all streams
- [ ] Set up outbox table and relay (if needed)
- [ ] Implement dead letter queue handler and `move_to_dlq()` utility
- [ ] Add `ObservabilityMiddleware` to broker
- [ ] Set up consumer lag collection Taskiq task
- [ ] Configure Prometheus metrics and alerts (consumer lag, DLQ depth)
- [ ] Verify context propagation (correlation_id, trace_id) in integration tests
- [ ] Configure backpressure thresholds for time-sensitive streams
- [ ] Configure consumer criticality levels per stream

### Optional Components Checklist

**WebSocket Real-Time (if not using 29-multi-channel-gateway):**
- [ ] Implement WebSocket endpoint
- [ ] Set up pub/sub subscriptions
- [ ] Implement heartbeat handling
- [ ] Document reconnection behavior

**Audit Trail:**
- [ ] Create audit event table
- [ ] Define auditable operations
- [ ] Set up retention policy

---

## Dependencies on Other Documents

| Document | Relationship |
|----------|-------------|
| 02-core-principles.md | O3 (Bounded Resource Usage) — MAXLEN caps, backpressure. P6 (Idempotency) — exactly-once processing. |
| 05-core-module-structure.md | Events are the inter-module communication mechanism |
| 22-opt-frontend-architecture.md | WebSocket real-time updates consume events |
| 08-core-observability.md | Resilience event logging contract, trace context correlation, consumer lag metrics |
| 15-core-background-tasks.md | Outbox relay and lag collection run as scheduled tasks |
| 16-core-concurrency-and-resilience.md | Circuit breaker, retry, timeout patterns for consumer resilience |
| 31-ai-agentic-architecture.md | Agent lifecycle events published through this module |
| 32-ai-agentic-pydanticai.md | Agent execution events published through this module |
| 27-opt-multi-channel-gateway.md | Gateway pushes events to connected clients via WebSocket |
