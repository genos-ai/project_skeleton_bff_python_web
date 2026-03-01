# 21 - Deployment: Bare Metal

*Version: 2.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 2.0.0 (2026-03-01): Python 3.14. uvloop as standard event loop. Updated systemd units with graceful shutdown (TimeoutStopSec, KillSignal). Added py-spy for production debugging. Added OpenTelemetry production stack (Prometheus + Loki + Tempo + Grafana). Added file descriptor limit guidance. Added tini for containerised sidecar deployments. References 24-concurrency-and-resilience.md and 12-observability.md v3.
- 1.0.0 (2025-01-27): Initial generic deployment standard

---

## Context

Not every project runs on a cloud platform. Teams with dedicated servers, regulatory constraints that prohibit public cloud, or cost-sensitive deployments need a deployment model that runs directly on the host operating system — without Docker, Kubernetes, or managed services.

This module defines that model using standard Linux infrastructure: systemd for process management, nginx for reverse proxy and TLS termination, and a symlink-based release strategy that enables instant rollback. The key insight is that the deployment model should not constrain the scaling path — the same application code runs on a single server with everything co-located, then scales to separate database servers, multiple application servers behind a load balancer, and eventually managed services if the scale justifies the cost.

The application code is identical regardless of whether it deploys to bare metal or Azure (22). This document covers only the infrastructure: server setup, service configuration, release management, backup procedures, and monitoring integration. It implements the security standards (17) at the infrastructure level and integrates with background tasks (19) for worker and scheduler service definitions.

---

## Deployment Philosophy

### No Containers

Applications run directly on the host operating system. No Docker, no Kubernetes.

Rationale:
- Simpler debugging and troubleshooting
- Direct access to system resources
- No container orchestration complexity
- Lower overhead for small deployments

### Process Management: systemd

All services managed by systemd:
- Automatic restart on failure
- Log management via journald
- Service dependencies
- Resource limits
- **Graceful shutdown with configurable timeout** (see Service Configuration)

### Scaling Path

MVP to Production without re-architecture:
1. Single server with all components
2. Separate database to dedicated server
3. Add application servers behind load balancer
4. Add Redis cluster if needed
5. Managed services when scale justifies cost

---

## Server Setup

### Operating System

Standard: Ubuntu LTS (24.04 or latest LTS)

Rationale:
- Widely used, well documented
- Long-term support
- Good Python ecosystem support

### System Requirements

Minimum for MVP:
- CPU: 4 cores
- RAM: 8 GB
- Storage: 100 GB SSD

Recommended for production:
- CPU: 8+ cores
- RAM: 32+ GB
- Storage: 500+ GB SSD

### Initial Configuration

1. Update system packages
2. Configure firewall (ufw)
3. Setup SSH key authentication, disable password auth
4. Create application user (non-root)
5. Configure automatic security updates
6. Setup log rotation
7. **Set file descriptor limits** (see below)
8. **Install py-spy** for production debugging (see Monitoring)

### File Descriptor Limits

FastAPI services with connection pools, Redis connections, and concurrent HTTP clients consume file descriptors quickly. The default Linux limit (1,024) is sufficient for most cases but may need adjustment under high concurrency.

Add to `/etc/security/limits.d/{app-name}.conf`:
```
{app-user}  soft  nofile  65536
{app-user}  hard  nofile  65536
```

Also set in the systemd service unit (see Service Configuration).

---

## Python Environment

### Python Installation

Use pyenv for Python version management:
- Install pyenv
- Install **Python 3.14** (see 03-backend-architecture.md and 24-concurrency-and-resilience.md for version requirements)
- Create project-specific virtual environment

```bash
# Install Python 3.14 via pyenv
pyenv install 3.14
pyenv local 3.14

# Create virtual environment
python -m venv /opt/{app-name}/venv
```

### Virtual Environment

Each application has its own virtual environment:
- Location: `/opt/{app-name}/venv/`
- Owned by application user
- Activated by systemd service

### Dependency Installation

```bash
cd /opt/{app-name}
source venv/bin/activate
pip install -r requirements.txt
```

Pin pip and setuptools versions for reproducibility.

### Required Packages

Ensure these are in `requirements.txt` for all deployments:

```
uvicorn[standard]
uvloop
tenacity
aiobreaker
py-spy
```

`uvloop` is required per 03-backend-architecture.md. `tenacity` and `aiobreaker` are required per 24-concurrency-and-resilience.md. `py-spy` is required per 12-observability.md for production debugging.

---

## Application Deployment

### Directory Structure

```
/opt/{app-name}/
├── current/              # Symlink to active release
├── releases/             # Release directories
│   ├── 20260301_120000/
│   └── 20260301_150000/
├── shared/               # Persistent files
│   ├── logs/
│   └── uploads/
├── venv/                 # Virtual environment
└── .env                  # Environment variables
```

### Deployment Process

1. Create new release directory with timestamp
2. Clone/copy application code to release directory
3. Install dependencies in virtual environment
4. Run database migrations
5. Update `current` symlink to new release
6. Restart application service
7. Verify health checks (including circuit breaker states in `/health/detailed`)
8. Clean up old releases (keep last 5)

### Rollback

Rollback is symlink change:
1. Update `current` symlink to previous release
2. Restart application service
3. Verify health checks

Database rollback if needed (separate process with migration downgrade).

---

## Service Configuration

### systemd Service Unit: API

Location: `/etc/systemd/system/{app-name}-api.service`

```ini
[Unit]
Description=Application API
After=network.target postgresql.service redis.service

[Service]
Type=simple
User={app-user}
Group={app-user}
WorkingDirectory=/opt/{app-name}/current
EnvironmentFile=/opt/{app-name}/.env
ExecStart=/opt/{app-name}/venv/bin/uvicorn modules.backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --loop uvloop \
    --timeout-graceful-shutdown 30

# Graceful shutdown
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=35

# Restart policy
Restart=always
RestartSec=5

# Resource limits
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

**Key settings explained:**

| Setting | Value | Rationale |
|---------|-------|-----------|
| `--loop uvloop` | uvloop event loop | 2–4x faster than default (doc 24) |
| `--timeout-graceful-shutdown 30` | 30 seconds to drain | Matches shutdown sequence in doc 24 |
| `KillSignal=SIGTERM` | Graceful signal | Triggers FastAPI lifespan shutdown |
| `KillMode=mixed` | SIGTERM to main, SIGKILL to children | Clean shutdown for main process |
| `TimeoutStopSec=35` | 35 seconds before SIGKILL | 30s drain + 5s buffer |
| `LimitNOFILE=65536` | File descriptor limit | Prevents FD exhaustion under load |

### systemd Service Unit: Worker

Location: `/etc/systemd/system/{app-name}-worker.service`

```ini
[Unit]
Description=Taskiq Worker
After=network.target redis.service

[Service]
Type=simple
User={app-user}
Group={app-user}
WorkingDirectory=/opt/{app-name}/current
EnvironmentFile=/opt/{app-name}/.env
ExecStart=/opt/{app-name}/venv/bin/taskiq worker modules.backend.tasks.broker:broker --workers 2

# Graceful shutdown
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=35

# Restart policy
Restart=always
RestartSec=5

# Resource limits
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

### systemd Service Unit: Scheduler

Only one scheduler instance should run (see doc 19):

```ini
[Unit]
Description=Taskiq Scheduler
After=network.target redis.service

[Service]
Type=simple
User={app-user}
Group={app-user}
WorkingDirectory=/opt/{app-name}/current
EnvironmentFile=/opt/{app-name}/.env
ExecStart=/opt/{app-name}/venv/bin/taskiq scheduler modules.backend.tasks.scheduler:scheduler

# Restart policy
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Service Commands

```bash
sudo systemctl start {app-name}-api
sudo systemctl stop {app-name}-api
sudo systemctl restart {app-name}-api
sudo systemctl status {app-name}-api
sudo systemctl enable {app-name}-api  # Start on boot
```

### Multiple Services

For applications with multiple components:
- `{app-name}-api.service` - FastAPI application
- `{app-name}-worker.service` - Taskiq worker (background tasks)
- `{app-name}-scheduler.service` - Taskiq scheduler (cron jobs)

Use `PartOf=` and `Requires=` for dependencies.

### Graceful Shutdown

All services handle shutdown signals gracefully per **24-concurrency-and-resilience.md**:

| Step | Timeout | Action |
|------|---------|--------|
| 1 | 0s | Receive SIGTERM, mark unhealthy (readiness returns 503) |
| 2 | 0–3s | Wait for load balancer to remove instance |
| 3 | 3–30s | Drain in-flight requests |
| 4 | 30s | Force-close remaining connections |
| 5 | 30–35s | Close database/Redis pools, flush logs |
| 6 | 35s | Process exits (SIGKILL if still alive) |

---

## Reverse Proxy

### Standard: nginx

nginx serves as reverse proxy and static file server.

Configuration location: `/etc/nginx/sites-available/{app-name}`

### Configuration Elements

- Listen on 80 (redirect to 443)
- Listen on 443 with SSL
- Proxy pass to application (localhost:8000)
- WebSocket upgrade handling
- Static file serving if applicable
- Security headers

### SSL Certificates

Use Let's Encrypt with certbot:
- Automatic renewal via systemd timer
- Certificate in `/etc/letsencrypt/live/{domain}/`

---

## Database Deployment

### PostgreSQL Setup

1. Install PostgreSQL from official repository
2. Create database and user
3. Configure `pg_hba.conf` for application access
4. Configure backups

### Connection Security

- Application connects via localhost or private network
- SSL for remote connections
- Strong passwords, stored in environment variables

### Backup Configuration

Daily backups via pg_dump:
- Full database dump
- Compress with gzip
- Copy to backup location (separate disk or remote)
- Retention: 30 days

---

## Redis Deployment

### Installation

Install from official repository for latest stable version.

### Configuration

Key settings:
- maxmemory: Set based on available RAM
- maxmemory-policy: allkeys-lru
- appendonly: yes (if persistence needed)

### Security

- Bind to localhost only
- Require password (stored in environment)
- Disable dangerous commands

---

## Environment Management

### Environment Variables

Stored in `/opt/{app-name}/.env`:
- Not in version control
- Owned by application user, mode 600
- Loaded by systemd service

### Configuration Updates

1. Update .env file
2. Restart affected services
3. Verify health checks

### Secret Rotation

Process for rotating secrets:
1. Generate new secret
2. Update .env file
3. Restart services
4. Verify operation
5. Revoke old secret (if external)

---

## Monitoring and Observability

For the full observability standard — three pillars (logs, metrics, traces), profiling tools, and resilience event logging — see **12-observability.md**.

### Log Collection

Logs written to `/opt/{app-name}/shared/logs/`:
- Application logs (JSON format via structlog)
- Access logs
- Error logs

Log rotation via logrotate:
- Daily rotation
- Compress after 1 day
- Keep 30 days

### Health Check Monitoring

External monitoring service (UptimeRobot, Healthchecks.io, or similar):
- Check `/health` endpoint every minute
- Alert on failure
- Check `/health/ready` to detect dependency issues
- Check `/health/detailed` for circuit breaker states (authenticated)

### Production Debugging with py-spy

`py-spy` is installed in all production environments for zero-overhead debugging of running processes:

```bash
# Diagnose stuck or slow service — dump all thread stacks
py-spy dump --pid $(pgrep -f uvicorn)

# Record flame graph for 30 seconds
py-spy record -o /tmp/profile.svg --pid $(pgrep -f uvicorn) --duration 30

# Live top-like view of CPU usage by function
py-spy top --pid $(pgrep -f uvicorn)

# Inspect async task tree (Python 3.14)
python -m asyncio pstree $(pgrep -f uvicorn)
```

See **12-observability.md** Profiling section for the full diagnostic workflow.

### Production Observability Stack

For production deployments, deploy the full observability stack:

| Component | Tool | Purpose |
|-----------|------|---------|
| Traces | **OpenTelemetry Collector** | Receive and export distributed traces |
| Trace Storage | **Tempo** (or Jaeger) | Trace storage and querying |
| Metrics | **Prometheus** + **node_exporter** | Application and system metrics |
| Logs | **Loki** + **Promtail** | Log aggregation from JSONL files |
| Dashboards | **Grafana** | Visualization, alerting, trace-to-log correlation |

**Deployment topology (single server):**
```
                    ┌─────────────┐
                    │   Grafana   │ :3000
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼────┐ ┌────▼─────┐ ┌───▼───┐
        │Prometheus│ │   Loki   │ │ Tempo │
        │  :9090   │ │  :3100   │ │ :3200 │
        └─────▲────┘ └────▲─────┘ └───▲───┘
              │            │           │
        ┌─────┴────┐ ┌────┴─────┐ ┌───┴────────┐
        │  /metrics│ │ Promtail │ │ OTel       │
        │ endpoint │ │ (logs/)  │ │ Collector  │
        └──────────┘ └──────────┘ └────────────┘
```

OpenTelemetry is configured in the application via `config/settings/observability.yaml` (see doc 12). The infrastructure components above are deployed as systemd services alongside the application.

**OpenCensus is deprecated.** Do not use `opencensus-ext-*` packages. Use OpenTelemetry exclusively.

### Resource Monitoring

System-level monitoring via Prometheus + node_exporter:
- CPU usage
- Memory usage
- Disk usage and I/O
- Network throughput
- Open file descriptors
- Process counts

---

## Scaling Considerations

### Vertical Scaling

First scaling step: Larger server
- More CPU for concurrent requests
- More RAM for database caching
- Faster storage for database

### Horizontal Scaling

When single server insufficient:

**Database:**
- Move to dedicated server
- Consider managed PostgreSQL
- Read replicas if read-heavy

**Application:**
- Multiple application servers
- Load balancer (nginx or cloud LB)
- Stateless backend — no sticky sessions needed

**Redis:**
- Move to dedicated server
- Redis Sentinel for HA
- Redis Cluster for scaling

**Workers:**
- Multiple workers across servers
- Same queue, competing consumers
- Scheduler runs on single instance only

**Observability stack:**
- Move Prometheus, Loki, Tempo, Grafana to dedicated monitoring server
- Use remote write for Prometheus if needed

---

## Disaster Recovery

### Backup Verification

Monthly:
- Restore backup to test environment
- Verify data integrity
- Test application against restored data

### Recovery Procedures

Documented procedures for:
- Full server failure
- Database corruption
- Accidental data deletion
- Security breach

### Recovery Time Objectives

Define and test:
- RPO (Recovery Point Objective): Maximum data loss acceptable
- RTO (Recovery Time Objective): Maximum downtime acceptable

Typical targets:
- RPO: 1 hour (continuous WAL archiving)
- RTO: 4 hours (restore from backup)

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tests passing
- [ ] Code reviewed and approved
- [ ] Database migrations tested
- [ ] Environment variables prepared
- [ ] Rollback plan documented
- [ ] Python 3.14 installed via pyenv
- [ ] uvloop and resilience packages in requirements.txt

### Deployment

- [ ] Notify team of deployment
- [ ] Deploy to staging, verify
- [ ] Deploy to production
- [ ] Verify health checks (`/health`, `/health/ready`, `/health/detailed`)
- [ ] Smoke test critical paths
- [ ] Verify circuit breaker states in `/health/detailed`

### Post-Deployment

- [ ] Monitor error rates (Grafana)
- [ ] Monitor response latency (Prometheus)
- [ ] Monitor consumer lag (if events module adopted)
- [ ] Confirm no regressions
- [ ] Update deployment log
- [ ] Clean up old releases

---

## Dependencies on Other Documents

| Document | Relationship |
|----------|-------------|
| 03-backend-architecture.md | Python 3.14, uvloop, FastAPI configuration |
| 12-observability.md | Production stack (Prometheus, Loki, Tempo, Grafana), profiling tools, health check specification |
| 17-security-standards.md | Server hardening, TLS, firewall configuration |
| 19-background-tasks.md | Worker and scheduler systemd service definitions |
| 22-deployment-azure.md | Alternative deployment target — same application code |
| 24-concurrency-and-resilience.md | Graceful shutdown sequence, uvloop, file descriptor limits |
