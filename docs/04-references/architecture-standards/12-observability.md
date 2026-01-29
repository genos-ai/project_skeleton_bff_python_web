# 12 - Observability

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic observability standard

---

## Logging

### Standard: structlog

All Python applications use structlog for structured logging.

Rationale:
- Structured JSON output for parsing
- Context binding across request
- Compatible with standard logging
- Easy to query and analyze

### Log Format

Production logs output as JSON with these fields:
- `timestamp`: ISO8601 UTC
- `level`: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `logger`: Module/component name
- `message`: Human-readable message
- `request_id`: Correlation ID for request tracing
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

**Never log:**
- Passwords or tokens
- Full credit card numbers
- Personal data beyond identifiers
- Request/response bodies with sensitive data

### Log Storage

Logs written to files with rotation:
- Location: `/var/log/{application}/` or `./logs/`
- Rotation: Daily or when file exceeds 100MB
- Retention: 30 days minimum
- Compression: Gzip after rotation

### Centralized Logging

For multi-service deployments:
- Aggregate logs to central location
- Use log shipper (Filebeat, Fluentd)
- Store in searchable system (Elasticsearch, Loki)

Centralization is recommended but not required for single-service deployments.

---

## Request Tracing

### Request ID

Every request receives unique identifier:
- Generated at API gateway entry
- Propagated to all downstream calls
- Included in all log entries
- Returned in response headers

Header: `X-Request-ID`

### Distributed Tracing

For multi-service architectures:
- Propagate trace context between services
- Record span timing for each service
- Use W3C Trace Context format

Implementation deferred until multi-service deployment.

---

## Metrics

### Application Metrics

Track these metrics for all services:

**Request metrics:**
- Request count by endpoint and status
- Request duration (p50, p95, p99)
- Request size
- Error rate

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

### Metric Format

Use Prometheus format for metrics:
- Counter for cumulative values
- Gauge for current values
- Histogram for distributions
- Labels for dimensions

### Metric Collection

Options (implement as needed):
- Prometheus scraping
- StatsD push
- Custom endpoint

For MVP: Expose metrics endpoint, collect manually or on-demand.

---

## Health Checks

### Endpoint Structure

Three health endpoints:

**`/health`** - Liveness
- Returns 200 if process is running
- No dependency checks
- Used by process monitors

**`/health/ready`** - Readiness
- Returns 200 if ready to serve traffic
- Checks critical dependencies (database, Redis)
- Used by load balancers

**`/health/detailed`** - Component Status
- Returns status of each component
- Authentication required
- Used for debugging

### Response Format

```json
{
  "status": "healthy",
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
  "timestamp": "2025-01-27T12:00:00Z"
}
```

### Health Check Implementation

- Checks must be fast (< 1 second total)
- Use simple queries (SELECT 1, PING)
- Cache results briefly to prevent overload
- Fail open for non-critical dependencies

---

## Error Tracking

### Error Capture

All unhandled exceptions captured with:
- Full stack trace
- Request context (URL, method, user)
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

---

## Alerting

### Alert Categories

| Category | Response Time | Examples |
|----------|---------------|----------|
| Critical | Immediate | Service down, data loss risk |
| Warning | Hours | High error rate, resource pressure |
| Info | Next business day | Unusual patterns, approaching limits |

### Alert Channels

- Critical: SMS/phone + email
- Warning: Email + chat (Slack/Discord)
- Info: Email or dashboard

### Alert Fatigue Prevention

- No alerts for self-healing issues
- Aggregate related alerts
- Clear escalation path
- Regular review of alert thresholds

---

## Performance Monitoring

### Slow Query Detection

Log queries exceeding threshold:
- Default threshold: 100ms
- Include query (without parameters), duration, caller
- Review periodically, add indexes or optimize

### Slow Request Detection

Log requests exceeding threshold:
- Default threshold: 1 second
- Include endpoint, method, duration, user
- Breakdown by component (database, external calls)

### Resource Monitoring

Monitor and alert on:
- Database connection pool exhaustion
- Redis memory usage
- Disk space
- Process memory growth

---

## Debugging

### Debug Mode

Applications support debug mode:
- Enabled via environment variable
- More verbose logging
- Detailed error responses (development only)
- Performance profiling available

### Log Level Override

Runtime log level changes:
- Via environment variable (requires restart)
- Via admin API (no restart, temporary)

### Request Debugging

For specific request troubleshooting:
- Enable debug logging for specific user/request
- Capture full request/response for replay
- Time each component of request processing

---

## Dashboard

### Essential Dashboards

**Operations Dashboard:**
- Service health status
- Request rate and latency
- Error rate
- Resource utilization

**Business Dashboard:**
- Active users
- Key business metrics
- Trend comparisons

### Dashboard Tools

Use Grafana or similar for dashboards.

For MVP: Text-based status scripts are acceptable. Full dashboards as scale requires.

---

## Runbooks

### Runbook Content

For each alert type, document:
- What the alert means
- Potential causes
- Investigation steps
- Resolution procedures
- Escalation path

### Runbook Location

Store runbooks with documentation:
- Version controlled
- Linked from alerts
- Reviewed and updated regularly

---

## Log Retention

### Retention Policy

| Log Type | Retention |
|----------|-----------|
| Application logs | 30 days |
| Access logs | 90 days |
| Audit logs | 1 year minimum |
| Debug logs | 7 days |

Adjust based on compliance requirements.

### Log Archival

After retention period:
- Compress and archive to cold storage
- Or delete if not required

Implement automated cleanup to prevent disk exhaustion.
