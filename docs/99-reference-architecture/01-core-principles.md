# 01 - Core Principles

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic principles document

---

## Mandatory Principles

These principles are non-negotiable. All architectural decisions must align with them.

### P1: Backend Owns All Business Logic

Every business rule, validation, calculation, and decision lives in the backend. Clients display results; they do not compute them.

Implications:
- Data calculations happen server-side
- Input validation happens server-side
- User permission checks happen server-side
- Data transformations happen server-side

### P2: Clients Are Stateless Presentation Layers

Clients maintain only UI state (which tab is selected, whether a modal is open). All application state comes from the backend via API calls or real-time connections.

Implications:
- Refresh the page, application state persists
- Switch clients (web to CLI), same data available
- Client bugs cannot corrupt application state

### P3: Single Database of Record

One authoritative data store per data type. No data synchronization between databases for the same entity. Read replicas are acceptable; multiple write sources are not.

Implications:
- User data lives in PostgreSQL only
- Cache is ephemeral, not authoritative

### P4: Explicit Over Implicit

Configuration is explicit. Dependencies are declared. Side effects are documented. Nothing happens "magically."

Implications:
- No auto-discovery of services
- No implicit type coercion
- No hidden global state
- All environment variables documented

### P5: Fail Fast, Fail Loudly

Errors surface immediately with clear messages. Silent failures are forbidden. Systems should not continue operating with corrupted or uncertain state.

Implications:
- Missing configuration fails at startup, not at first use
- Invalid data raises exceptions, not default values
- All errors are logged with context

### P6: Idempotency for All Operations

Operations can be safely retried. Duplicate requests produce the same result as single requests. This enables reliable recovery from network failures.

Implications:
- Create operations check for existing records
- Update operations use version checks or timestamps
- Delete operations succeed even if already deleted
- Critical operations use idempotency keys

### P7: No Hardcoded Values

All configurable values come from configuration files or environment variables. Magic numbers, URLs, credentials, and feature flags never appear in code.

Implications:
- Environment-specific values in .env files
- Application settings in YAML configuration
- Secrets in environment variables only

---

## Structural Principles

### S1: Layered Architecture

Backend services follow strict layering:

1. **API Layer** - HTTP handlers, request/response transformation
2. **Service Layer** - Business logic, orchestration
3. **Repository Layer** - Data access, queries
4. **Model Layer** - Data structures, entities

Each layer only calls the layer directly below it. No skipping layers. No upward calls.

### S2: Dependency Injection

Services receive their dependencies through constructors, not global imports or service locators. This enables testing and makes dependencies explicit.

### S3: Interface Segregation

Clients receive only the data they need. API responses are shaped for consumer needs, not database structure. Different clients may receive different response shapes for the same underlying data.

### S4: Separation of Concerns

Each module has one responsibility. Authentication does not handle user profile updates. Order processing does not handle inventory management. Clear boundaries enable independent development and testing.

---

## Operational Principles

### O1: Observable by Default

All services emit structured logs. Key operations include timing. Errors include stack traces. Health endpoints expose service status.

### O2: Graceful Degradation

When non-critical dependencies fail, the system continues operating with reduced functionality. A failed recommendation engine does not prevent core operations.

### O3: Bounded Resource Usage

All operations have timeouts. All queries have limits. All queues have maximum sizes. Unbounded operations do not exist.

### O4: Reversible Changes

Database migrations include rollback scripts. Feature deployments use feature flags. Configuration changes can be reverted without code deployment.

---

## Development Principles

### D1: Consistent Patterns

Similar problems receive similar solutions. If user authentication uses JWT, service authentication uses JWT. If one API returns paginated results with cursor-based navigation, all paginated APIs do.

### D2: Documentation as Code

Architecture decisions are documented. API contracts are specified. Database schemas include comments. If it is not documented, it does not exist for other developers.

### D3: Test Critical Paths

Not everything requires tests. Critical paths require tests. A critical path is any operation where failure causes data loss, financial loss, or security breach.

### D4: Version Everything

APIs are versioned. Configuration schemas are versioned. Database migrations are versioned. Breaking changes are never introduced without version increment.
