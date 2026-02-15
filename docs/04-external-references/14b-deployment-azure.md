# 14b - Deployment: Azure

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-02-14*

## Changelog

- 1.0.0 (2025-02-14): Initial Azure deployment standard

---

## Relationship to 14-Deployment

Document 14 defines deployment for self-hosted bare-metal infrastructure (Ubuntu + systemd + nginx). This document defines an alternative deployment target using Azure managed services. Projects choose one deployment model. Both follow the same application architecture — the backend code, service layer, and repository patterns are identical regardless of deployment target.

Choose this document when:
- The hosting organisation mandates Azure
- Managed services reduce operational burden (no patching, no HA configuration)
- Integration with Entra ID, Azure OpenAI, or other Azure-native services is required
- CI/CD runs through Azure DevOps

Choose 14-Deployment (bare-metal) when:
- Full infrastructure control is required
- Cost sensitivity favours fixed compute over consumption-based billing
- Regulatory requirements prohibit public cloud
- The team has dedicated infrastructure operations capacity

---

## Deployment Philosophy

### Managed Services First

Applications use Azure managed services for all supporting infrastructure. The team operates application code, not infrastructure.

Rationale:
- Patching, HA, and backups handled by Azure
- Managed identity eliminates credential management for Azure-to-Azure communication
- Private endpoints keep data-plane traffic off the public internet
- Consumption scales with demand without capacity planning

### No Containers

Consistent with 14-Deployment: applications run directly on the platform runtime, not in containers. Azure App Service provides native Python support on Linux without Docker.

Exception: If the project already requires containerisation for other reasons (multi-language polyglot, GPU workloads, sidecar patterns), use Azure Container Apps instead. Do not use AKS unless the organisation already operates an AKS cluster.

### No Azure Functions for API Backends

Azure Functions is not used as the primary backend for web applications or chatbots.

Rationale:
- 230-second HTTP trigger timeout is insufficient for LLM-backed conversations
- Cold start latency (3-10 seconds on Consumption plan) degrades UX
- WebSocket support is limited
- Debugging multi-turn conversations across ephemeral invocations is painful

Azure Functions is appropriate only for isolated, short-lived event handlers (webhook receivers, queue processors) that complement the primary backend.

---

## Compute: Azure App Service

### Standard: App Service on Linux (Python)

All Python web applications deploy to Azure App Service on Linux with the native Python runtime.

### SKU Selection

| Environment | SKU | vCPU | RAM | Use Case |
|-------------|-----|------|-----|----------|
| Development | B1 | 1 | 1.75 GB | Local-equivalent for dev/test |
| Staging | P1v3 | 2 | 8 GB | Pre-production validation |
| Production | P2v3 | 4 | 16 GB | Production workloads |
| Production (LLM-heavy) | P3v3 | 8 | 32 GB | High-concurrency LLM orchestration |

Premium v3 (Pv3) is mandatory for production. It provides VNet integration, deployment slots, and auto-scale — none of which are available on Basic or Standard tiers.

### Runtime Configuration

| Setting | Value |
|---------|-------|
| Runtime stack | Python 3.12 |
| Startup command | `gunicorn -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 modules.backend.main:app` |
| Always On | Enabled (prevents idle unload) |
| ARR Affinity | Disabled (stateless backend; session state in Redis/PostgreSQL) |
| HTTPS Only | Enabled |
| Minimum TLS | 1.2 |
| FTP State | Disabled |
| Remote debugging | Disabled in production |
| Platform | 64-bit |

### Worker Configuration

Gunicorn worker count follows the formula: `(2 × vCPU) + 1` as a starting point. For LLM-backed applications where most time is spent waiting on external APIs (I/O-bound), fewer workers with async handling is more efficient than many workers:

| SKU | vCPU | Recommended Workers | Rationale |
|-----|------|---------------------|-----------|
| B1 | 1 | 2 | Development only |
| P1v3 | 2 | 2–3 | Each worker handles many concurrent async requests |
| P2v3 | 4 | 3–4 | Scale via async concurrency, not worker count |
| P3v3 | 8 | 4–6 | Diminishing returns beyond this |

Each Uvicorn worker handles hundreds of concurrent async connections. Do not over-allocate workers — each consumes memory for its own copy of the application.

### WebSocket Support

App Service supports WebSocket connections natively. Enable in the Azure portal or Terraform:

```hcl
resource "azurerm_linux_web_app" "backend" {
  site_config {
    websocket_enabled = true
  }
}
```

WebSocket connections on App Service have a **240-minute idle timeout**. The application must implement heartbeat/keepalive per 06-event-architecture.md (30-second ping interval) to prevent premature disconnection.

### Deployment Slots

Production App Service uses deployment slots for zero-downtime releases:

| Slot | Purpose |
|------|---------|
| `production` | Live traffic |
| `staging` | Pre-release validation, swap target |

Deployment flow:
1. Deploy new code to `staging` slot
2. Run smoke tests against staging URL
3. Swap `staging` ↔ `production` (instant, no restart)
4. If issues detected, swap back (instant rollback)

Slot-specific settings (not swapped):
- Database connection strings (staging points to staging DB)
- `APP_ENV` environment variable
- Application Insights instrumentation key (separate telemetry)

Slot settings are marked with `"sticky": true` in Terraform or configured as "Deployment slot setting" in the portal.

### Application Settings

All configuration is injected via App Service Application Settings, which surface as environment variables to the application. This is compatible with the existing `config.py` pattern using `pydantic-settings` and `python-dotenv`.

Settings are organised into three categories:

**1. Plain-text settings** (set directly):
```
APP_ENV=production
APP_LOG_LEVEL=info
APP_DEBUG=false
CORS_ORIGINS=["https://chatbot.icarus.com"]
SAILPOINT_BASE_URL=https://icarus.api.identitynow.com
AZURE_OPENAI_ENDPOINT=https://icarus-openai.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o
LLM_PROVIDER=azure_openai
```

**2. Key Vault references** (secrets):
```
SAILPOINT_CLIENT_ID=@Microsoft.KeyVault(VaultName=icarus-chatbot-kv;SecretName=sailpoint-client-id)
SAILPOINT_CLIENT_SECRET=@Microsoft.KeyVault(VaultName=icarus-chatbot-kv;SecretName=sailpoint-client-secret)
DATABASE_URL=@Microsoft.KeyVault(VaultName=icarus-chatbot-kv;SecretName=database-url)
REDIS_URL=@Microsoft.KeyVault(VaultName=icarus-chatbot-kv;SecretName=redis-url)
```

**3. Managed identity** (no credentials needed):
Azure OpenAI and Key Vault use managed identity authentication. No API keys or connection strings stored for these services.

### Custom Domain & TLS

| Setting | Value |
|---------|-------|
| Custom domain | `chatbot.icarus.com` (CNAME to `*.azurewebsites.net`) |
| TLS certificate | App Service Managed Certificate (free, auto-renewed) or corporate CA certificate |
| Minimum TLS version | 1.2 |
| HTTPS redirect | Enforced at App Service level |

No nginx reverse proxy. App Service handles TLS termination, HTTPS redirect, and load balancing natively.

---

## Database: Azure Database for PostgreSQL

### Standard: Flexible Server

| Setting | Value |
|---------|-------|
| Engine | PostgreSQL 16 |
| SKU | Burstable B2ms (dev) / General Purpose D4ds_v5 (prod) |
| Storage | 128 GB (auto-grow enabled) |
| High Availability | Zone-redundant (production only) |
| Backup retention | 35 days |
| Geo-redundant backup | Enabled for production |

### Network Access

PostgreSQL Flexible Server is deployed with **private access** (VNet integration). No public endpoint.

The server is placed in a delegated subnet within the application VNet. App Service connects via VNet integration — traffic never traverses the public internet.

### Connection Configuration

Connection string format:
```
postgresql+asyncpg://{user}:{password}@{server}.postgres.database.azure.com:5432/{database}?sslmode=require
```

The full connection string is stored in Key Vault as a single secret. App Service references it via:
```
DATABASE_URL=@Microsoft.KeyVault(VaultName=icarus-chatbot-kv;SecretName=database-url)
```

### Connection Pooling

Azure PostgreSQL Flexible Server includes built-in PgBouncer. Enable it instead of running a separate pooler:

| Parameter | Value |
|-----------|-------|
| PgBouncer | Enabled |
| Pool mode | Transaction |
| Default pool size | 50 |
| Min pool size | 10 |
| Server idle timeout | 600 |

Application-side (SQLAlchemy):

```python
engine = create_async_engine(
    settings.database_url,
    pool_size=10,          # Per-worker pool
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=1800,     # Recycle connections every 30 min
    pool_pre_ping=True,    # Verify connection before use
)
```

### Migrations

Alembic migrations run as a pre-deployment step in the CI/CD pipeline, not at application startup:

```yaml
# In azure-pipelines.yml, deploy stage:
- script: |
    source .venv/bin/activate
    alembic upgrade head
  env:
    DATABASE_URL: $(DATABASE_URL)
  displayName: 'Run database migrations'
```

Never run migrations in the startup command. If a migration fails, it must block deployment — not crash the running application.

### Backup & Recovery

| Parameter | Value |
|-----------|-------|
| Automated backup | Daily (Azure-managed) |
| Backup retention | 35 days |
| Point-in-time restore | Any point within retention window |
| Geo-redundant backup | Enabled (production) |
| RPO | 5 minutes (continuous WAL archiving) |
| RTO | < 1 hour (point-in-time restore) |

Test restore monthly by restoring to a temporary server and validating data integrity. Document and automate the procedure.

---

## Cache: Azure Cache for Redis

### Standard: Azure Cache for Redis (Premium)

| Setting | Value |
|---------|-------|
| SKU | Premium P1 (6 GB) |
| Redis version | 7.x |
| TLS | Required (port 6380) |
| Non-TLS port | Disabled |
| Clustering | Disabled (enable when > 50 GB needed) |

### Network Access

Premium tier supports **private endpoints**. Deploy a private endpoint in the PE subnet. No public network access.

### Use Cases

| Purpose | Redis Database | TTL |
|---------|---------------|-----|
| Session cache | 0 | 1 hour |
| LangGraph conversation state | 1 | 4 hours |
| Taskiq task broker | 2 | Per task |
| Rate limiting counters | 3 | Per window |
| SailPoint token cache | 4 | 12 minutes (token lifetime minus buffer) |

### Connection

```python
# In config.py
redis_url: str = "rediss://:password@hostname:6380/0"  # Note: rediss:// (with TLS)
```

Connection string stored in Key Vault. `rediss://` scheme enforces TLS.

### Redis for Taskiq

The existing Taskiq + Redis pattern from the skeleton works unchanged. Taskiq connects using the same Redis instance (different database number). The Taskiq worker runs as a **separate App Service** or as a **WebJob** attached to the main App Service:

**Option A: Separate App Service (recommended for production)**

Dedicated App Service for the worker process, same VNet integration:
```bash
# Startup command for worker App Service
taskiq worker modules.backend.tasks.broker:broker
```

**Option B: WebJob (simpler, acceptable for low-volume)**

Continuous WebJob attached to the main App Service:
```bash
# run.sh in the WebJob zip
source /home/site/wwwroot/.venv/bin/activate
cd /home/site/wwwroot
taskiq worker modules.backend.tasks.broker:broker
```

### Scheduler

The Taskiq scheduler must run as a singleton (one instance only). Deploy as a separate continuous WebJob with `is_singleton: true`, or as a dedicated App Service scaled to exactly 1 instance.

```bash
# Scheduler startup
taskiq scheduler modules.backend.tasks.scheduler:scheduler
```

---

## Secrets: Azure Key Vault

### Standard: Key Vault with RBAC Authorization

| Setting | Value |
|---------|-------|
| SKU | Standard |
| Access model | Azure RBAC (not access policies) |
| Soft delete | Enabled (90-day retention) |
| Purge protection | Enabled (production) |
| Network access | Private endpoint only |

### Secret Naming Convention

Format: `{app}-{component}-{purpose}`

| Secret Name | Content |
|-------------|---------|
| `chatbot-db-connection-string` | Full PostgreSQL connection string |
| `chatbot-redis-connection-string` | Full Redis connection string |
| `chatbot-sailpoint-client-id` | SailPoint OAuth2 client ID |
| `chatbot-sailpoint-client-secret` | SailPoint OAuth2 client secret |
| `chatbot-anthropic-api-key` | Anthropic API key (if using Claude) |

### Access Control

| Principal | Role | Scope |
|-----------|------|-------|
| App Service managed identity | Key Vault Secrets User | Key Vault resource |
| CI/CD service principal | Key Vault Secrets User | Key Vault resource |
| Security team (break-glass) | Key Vault Administrator | Key Vault resource |
| Developers | None | No direct access in production |

Never assign Key Vault Secrets Officer to application identities. Officer includes delete/purge permissions.

### App Service Integration

App Service references Key Vault secrets directly in Application Settings using the `@Microsoft.KeyVault()` syntax. This requires:

1. App Service has a system-assigned managed identity (enabled)
2. Managed identity has `Key Vault Secrets User` role on the Key Vault
3. Key Vault allows access from the App Service VNet (private endpoint or service endpoint)

App Service resolves the reference at startup and on settings refresh. Secret rotation requires restarting the App Service (or triggering a settings refresh) to pick up new values.

### Secret Rotation

Process for rotating secrets:

1. Generate new secret value
2. Add new version to Key Vault (old version remains active)
3. Restart App Service to pick up new reference
4. Verify application health
5. Disable old secret version in Key Vault after confirmation period (24 hours)
6. Record rotation in audit log

Automate rotation for SailPoint credentials on a 90-day cycle. Azure Key Vault supports rotation policies with Event Grid notifications.

---

## Identity: Managed Identities

### Principle: No Credentials for Azure-to-Azure

Azure-managed services authenticate to each other using managed identities. No API keys, passwords, or connection strings for Azure-to-Azure communication.

### System-Assigned Managed Identity

The App Service has a system-assigned managed identity. This identity authenticates to:

| Target Service | RBAC Role | Purpose |
|----------------|-----------|---------|
| Azure Key Vault | Key Vault Secrets User | Read application secrets |
| Azure OpenAI | Cognitive Services OpenAI User | LLM API access |
| Application Insights | Monitoring Metrics Publisher | Telemetry submission |

### Code Pattern

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# For Azure OpenAI (via openai library)
credential = DefaultAzureCredential()
token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

client = openai.AzureOpenAI(
    azure_endpoint=settings.azure_openai_endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2024-12-01-preview",
)
```

`DefaultAzureCredential` automatically uses the managed identity in Azure and developer credentials locally (via Azure CLI or VS Code). No conditional logic required.

### Local Development

Developers authenticate using Azure CLI:
```bash
az login
```

`DefaultAzureCredential` picks this up automatically. The same code works in both environments.

---

## LLM: Azure OpenAI

### Standard: Azure OpenAI Service

| Setting | Value |
|---------|-------|
| Model | GPT-4o (deployment name: `gpt-4o`) |
| API version | `2024-12-01-preview` or latest stable |
| Authentication | Managed identity (Entra ID token) |
| Network access | Private endpoint only |
| Content filtering | Default (Standard) |
| Tokens per minute (TPM) | 120K minimum for production |

### Network Configuration

Azure OpenAI is accessed via private endpoint. The App Service connects over the VNet backbone — no public internet traversal.

### Quota & Throttling

| Deployment | TPM | RPM | Purpose |
|------------|-----|-----|---------|
| `gpt-4o` | 120K | 720 | Primary chat and tool calling |
| `gpt-4o-mini` | 200K | 1200 | Item summarisation, classification |

Implement client-side retry with exponential backoff for 429 responses:

```python
# In services/llm/provider.py
RETRY_CONFIG = {
    "max_retries": 3,
    "initial_delay": 1.0,
    "backoff_factor": 2.0,
    "retry_on_status": [429, 500, 502, 503],
}
```

### Anthropic Alternative

If using Anthropic Claude instead of (or alongside) Azure OpenAI:

| Setting | Value |
|---------|-------|
| API endpoint | `https://api.anthropic.com` or enterprise endpoint |
| Authentication | API key (stored in Key Vault) |
| Model | `claude-sonnet-4-5-20250929` |

Anthropic does not offer private endpoints or VNet integration. Traffic flows over the public internet (TLS-encrypted). For regulated workloads, confirm data processing terms with Anthropic and ensure the enterprise agreement covers zero data retention.

The LLM provider abstraction in `services/llm/provider.py` handles both backends. The choice is configuration, not code.

---

## Networking

### VNet Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  VNet: chatbot-vnet (10.0.0.0/16)                           │
│                                                             │
│  ┌─────────────────────────────────┐                        │
│  │  Subnet: app-subnet             │                        │
│  │  10.0.1.0/24                    │                        │
│  │  Delegation: Microsoft.Web      │                        │
│  │                                 │                        │
│  │  ┌───────────────────────────┐  │                        │
│  │  │ App Service VNet          │  │                        │
│  │  │ Integration (outbound)    │  │                        │
│  │  └───────────────────────────┘  │                        │
│  └─────────────────────────────────┘                        │
│                                                             │
│  ┌─────────────────────────────────┐                        │
│  │  Subnet: pe-subnet              │                        │
│  │  10.0.2.0/24                    │                        │
│  │                                 │                        │
│  │  Private Endpoints:             │                        │
│  │  - Azure OpenAI                 │                        │
│  │  - Key Vault                    │                        │
│  │  - Redis                        │                        │
│  │                                 │                        │
│  └─────────────────────────────────┘                        │
│                                                             │
│  ┌─────────────────────────────────┐                        │
│  │  Subnet: db-subnet              │                        │
│  │  10.0.3.0/24                    │                        │
│  │  Delegation: Microsoft.DBfor... │                        │
│  │                                 │                        │
│  │  PostgreSQL Flexible Server     │                        │
│  │  (VNet-integrated)              │                        │
│  └─────────────────────────────────┘                        │
│                                                             │
│  ┌─────────────────────────────────┐                        │
│  │  Subnet: mgmt-subnet            │                        │
│  │  10.0.4.0/24                    │                        │
│  │                                 │                        │
│  │  Azure Bastion (optional)       │                        │
│  └─────────────────────────────────┘                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │
         │ Outbound to SailPoint IDN (public HTTPS)
         ▼
    SailPoint IdentityNow SaaS
    (*.api.identitynow.com)
```

### Network Security Groups

| NSG | Rule | Source | Destination | Port | Action |
|-----|------|--------|-------------|------|--------|
| app-nsg | AllowVNetOutbound | app-subnet | pe-subnet, db-subnet | 443, 5432, 6380 | Allow |
| app-nsg | AllowSailPointOutbound | app-subnet | Internet | 443 | Allow |
| app-nsg | DenyAllOutbound | app-subnet | * | * | Deny |
| pe-nsg | AllowFromApp | app-subnet | pe-subnet | 443, 6380 | Allow |
| pe-nsg | DenyAll | * | pe-subnet | * | Deny |
| db-nsg | AllowFromApp | app-subnet | db-subnet | 5432 | Allow |
| db-nsg | DenyAll | * | db-subnet | * | Deny |

### DNS

Private endpoints require Private DNS Zones for name resolution:

| Service | Private DNS Zone |
|---------|-----------------|
| Azure OpenAI | `privatelink.openai.azure.com` |
| Key Vault | `privatelink.vaultcore.azure.net` |
| Redis | `privatelink.redis.cache.windows.net` |
| PostgreSQL | `privatelink.postgres.database.azure.com` |

Link all Private DNS Zones to the VNet. App Service resolves private endpoint FQDNs via these zones automatically.

### Outbound Traffic

App Service VNet integration routes **all outbound traffic** through the VNet (set `vnetRouteAllEnabled: true`). This ensures:
- Traffic to Azure services flows through private endpoints
- Traffic to SailPoint exits through a controlled path
- NSG rules apply to all outbound connections

SailPoint IdentityNow is a SaaS service with no private connectivity option. Outbound HTTPS to `*.api.identitynow.com` is the only traffic that traverses the public internet. This is TLS-encrypted and authenticated via OAuth2.

---

## Frontend: Azure Static Web Apps

### Standard: Static Web Apps (Standard tier)

The React/Vite frontend deploys to Azure Static Web Apps, separate from the backend.

| Setting | Value |
|---------|-------|
| SKU | Standard |
| Build | Vite (`npm run build` → `dist/`) |
| Custom domain | `chatbot.icarus.com` |
| API proxy | Reverse proxy to App Service backend |

### Reverse Proxy Configuration

`staticwebapp.config.json` in the frontend root:

```json
{
  "routes": [
    {
      "route": "/api/*",
      "rewrite": "https://icarus-chatbot-backend.azurewebsites.net/api/*"
    },
    {
      "route": "/ws/*",
      "rewrite": "https://icarus-chatbot-backend.azurewebsites.net/ws/*"
    }
  ],
  "navigationFallback": {
    "rewrite": "/index.html",
    "exclude": ["/api/*", "/ws/*", "/assets/*"]
  },
  "globalHeaders": {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; connect-src 'self' wss://icarus-chatbot-backend.azurewebsites.net"
  }
}
```

### Alternative: Serve from App Service

For simpler deployments, the Vite build output can be served as static files from the FastAPI backend. This eliminates a separate service but couples frontend and backend deployments.

```python
# In main.py
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="modules/frontend/dist", html=True), name="frontend")
```

Use Static Web Apps for production (CDN, edge caching, independent deployment). Use the App Service approach for development and staging.

---

## Monitoring: Application Insights

### Standard: Application Insights (workspace-based)

| Setting | Value |
|---------|-------|
| SKU | Workspace-based |
| Log Analytics workspace | Shared with other team resources |
| Sampling | Adaptive (target 5 events/sec in production) |
| Retention | 90 days (extend for compliance if required) |

### Integration with structlog

The existing structlog setup from the skeleton continues to write JSON logs to stdout. App Service captures stdout and forwards to Application Insights automatically when the instrumentation is configured.

Add OpenCensus or OpenTelemetry for richer telemetry:

```txt
# In requirements.txt
opencensus-ext-azure>=1.1.0
opencensus-ext-requests>=0.8.0
opencensus-ext-logging>=0.1.0
```

```python
# In core/observability.py
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer

def setup_azure_monitoring(connection_string: str):
    """Configure Application Insights telemetry."""
    # Distributed tracing
    tracer = Tracer(
        exporter=AzureExporter(connection_string=connection_string),
        sampler=ProbabilitySampler(rate=1.0),  # 100% in dev, reduce in prod
    )
    
    # Log forwarding
    logger = logging.getLogger()
    logger.addHandler(AzureLogHandler(connection_string=connection_string))
```

### Key Metrics to Track

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Response time (P95) | App Insights | > 5 seconds |
| Error rate (5xx) | App Insights | > 1% of requests |
| LLM latency (P95) | Custom metric | > 10 seconds |
| LLM token cost (daily) | Custom metric | > budget threshold |
| SailPoint API errors | Custom metric | > 5 per hour |
| WebSocket connections | Custom metric | > 80% of worker capacity |
| CPU utilisation | App Service metrics | > 80% sustained |
| Memory utilisation | App Service metrics | > 85% sustained |
| Database connections | PostgreSQL metrics | > 80% of pool |
| Redis memory | Redis metrics | > 80% of max |

### Alerting

Configure alerts in Application Insights or Azure Monitor:

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| High error rate | 5xx > 5% for 5 min | Sev 1 | PagerDuty / Teams notification |
| App Service down | Health check fails 3 consecutive | Sev 0 | PagerDuty |
| LLM budget exceeded | Daily token cost > threshold | Sev 2 | Email notification |
| Database connection exhaustion | Active connections > 90% | Sev 1 | Teams notification |
| SailPoint API unreachable | 5 consecutive failures | Sev 1 | Teams notification |

---

## CI/CD: Azure DevOps Pipelines

### Pipeline Structure

Two pipelines:

| Pipeline | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | PR to `develop` or `main` | Build, test, lint, security scan |
| `cd.yml` | Merge to `main` | Deploy to staging, swap to production |

### CI Pipeline

```yaml
# azure-pipelines/ci.yml
trigger:
  branches:
    include:
      - develop
      - main
  paths:
    exclude:
      - docs/**
      - '*.md'

pr:
  branches:
    include:
      - develop
      - main

pool:
  vmImage: 'ubuntu-latest'

variables:
  pythonVersion: '3.12'

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '$(pythonVersion)'
    displayName: 'Use Python $(pythonVersion)'

  - script: |
      curl -LsSf https://astral.sh/uv/install.sh | sh
      source $HOME/.local/bin/env
      uv venv
      source .venv/bin/activate
      uv pip install -r requirements.txt
    displayName: 'Install dependencies'

  - script: |
      source .venv/bin/activate
      black --check modules/backend tests
      isort --check modules/backend tests
      flake8 modules/backend tests
    displayName: 'Lint'

  - script: |
      source .venv/bin/activate
      mypy modules/backend
    displayName: 'Type check'

  - script: |
      source .venv/bin/activate
      pytest --cov=modules/backend --cov-report=xml --cov-report=term-missing -m "not integration"
    displayName: 'Unit tests'

  - task: PublishTestResults@2
    inputs:
      testResultsFormat: 'JUnit'
      testResultsFiles: '**/test-results.xml'
    condition: always()

  - task: PublishCodeCoverageResults@2
    inputs:
      summaryFileLocation: '**/coverage.xml'
    condition: always()
```

### CD Pipeline

```yaml
# azure-pipelines/cd.yml
trigger:
  branches:
    include:
      - main

pool:
  vmImage: 'ubuntu-latest'

variables:
  pythonVersion: '3.12'
  azureSubscription: 'icarus-azure-connection'
  appServiceName: 'icarus-identity-chatbot'
  resourceGroup: 'rg-chatbot-prod'

stages:
  - stage: Build
    displayName: 'Build & Package'
    jobs:
      - job: Build
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '$(pythonVersion)'

          - script: |
              curl -LsSf https://astral.sh/uv/install.sh | sh
              source $HOME/.local/bin/env
              uv venv
              source .venv/bin/activate
              uv pip install -r requirements.txt
            displayName: 'Install dependencies'

          - script: |
              source .venv/bin/activate
              pytest -m "not integration" --tb=short
            displayName: 'Run tests'

          - task: ArchiveFiles@2
            inputs:
              rootFolderOrFile: '$(Build.SourcesDirectory)'
              includeRootFolder: false
              archiveType: 'zip'
              archiveFile: '$(Build.ArtifactStagingDirectory)/app.zip'
              replaceExistingArchive: true

          - publish: '$(Build.ArtifactStagingDirectory)/app.zip'
            artifact: 'app'

  - stage: DeployStaging
    displayName: 'Deploy to Staging Slot'
    dependsOn: Build
    jobs:
      - deployment: DeployStaging
        environment: 'staging'
        strategy:
          runOnce:
            deploy:
              steps:
                - download: current
                  artifact: 'app'

                - task: AzureCLI@2
                  displayName: 'Run database migrations'
                  inputs:
                    azureSubscription: '$(azureSubscription)'
                    scriptType: 'bash'
                    scriptLocation: 'inlineScript'
                    inlineScript: |
                      # Fetch DB URL from Key Vault
                      DB_URL=$(az keyvault secret show \
                        --vault-name icarus-chatbot-kv \
                        --name chatbot-db-connection-string \
                        --query value -o tsv)
                      
                      pip install -r requirements.txt
                      DATABASE_URL=$DB_URL alembic upgrade head

                - task: AzureWebApp@1
                  displayName: 'Deploy to staging slot'
                  inputs:
                    azureSubscription: '$(azureSubscription)'
                    appType: 'webAppLinux'
                    appName: '$(appServiceName)'
                    deployToSlotOrASE: true
                    slotName: 'staging'
                    resourceGroupName: '$(resourceGroup)'
                    package: '$(Pipeline.Workspace)/app/app.zip'
                    runtimeStack: 'PYTHON|3.12'
                    startUpCommand: >-
                      gunicorn -w 2 -k uvicorn.workers.UvicornWorker
                      -b 0.0.0.0:8000 modules.backend.main:app

  - stage: SmokeTest
    displayName: 'Smoke Test Staging'
    dependsOn: DeployStaging
    jobs:
      - job: SmokeTest
        steps:
          - script: |
              STAGING_URL="https://$(appServiceName)-staging.azurewebsites.net"
              
              # Health check
              HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$STAGING_URL/health")
              if [ "$HTTP_STATUS" != "200" ]; then
                echo "Health check failed: $HTTP_STATUS"
                exit 1
              fi
              
              # Readiness check
              HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$STAGING_URL/health/ready")
              if [ "$HTTP_STATUS" != "200" ]; then
                echo "Readiness check failed: $HTTP_STATUS"
                exit 1
              fi
              
              echo "Smoke tests passed"
            displayName: 'Health check staging'

  - stage: SwapToProduction
    displayName: 'Swap to Production'
    dependsOn: SmokeTest
    jobs:
      - deployment: SwapSlots
        environment: 'production'
        strategy:
          runOnce:
            deploy:
              steps:
                - task: AzureAppServiceManage@0
                  displayName: 'Swap staging → production'
                  inputs:
                    azureSubscription: '$(azureSubscription)'
                    Action: 'Swap Slots'
                    WebAppName: '$(appServiceName)'
                    ResourceGroupName: '$(resourceGroup)'
                    SourceSlot: 'staging'
```

### Rollback

Rollback is a slot swap in reverse:

```bash
az webapp deployment slot swap \
  --name icarus-identity-chatbot \
  --resource-group rg-chatbot-prod \
  --slot staging \
  --target-slot production
```

This is instant (sub-second) and does not require a redeployment.

---

## Scaling

### Scaling Path

MVP to production without re-architecture:

1. **Single App Service P1v3** — handles initial user base
2. **Scale up to P2v3/P3v3** — more CPU/RAM per instance
3. **Scale out (2-4 instances)** — auto-scale based on CPU or request count
4. **Separate worker App Service** — dedicated compute for background tasks
5. **Redis Premium with clustering** — if cache exceeds 6 GB
6. **PostgreSQL scale-up** — larger SKU for connection count / IOPS

### Auto-Scale Rules

Configure auto-scale on the App Service Plan:

| Metric | Scale Out | Scale In | Cooldown |
|--------|-----------|----------|----------|
| CPU % | > 70% for 10 min | < 30% for 10 min | 5 min |
| Request count | > 500/min per instance | < 100/min per instance | 5 min |

Limits:
- Minimum instances: 2 (production, for availability)
- Maximum instances: 6 (cost ceiling)

### Session Affinity

ARR Affinity is **disabled**. All session state lives in Redis and PostgreSQL. Any instance can serve any request. This is essential for horizontal scaling and slot swaps.

---

## Infrastructure as Code: Terraform

### Standard: Terraform with Azure Provider

All Azure resources are defined in Terraform. No manual portal provisioning for production.

### State Management

| Setting | Value |
|---------|-------|
| Backend | Azure Storage Account (blob) |
| State file | `terraform.tfstate` |
| State locking | Azure Blob lease |
| State encryption | Storage Account encryption (SSE) |

### Module Structure

```
infrastructure/
├── terraform/
│   ├── main.tf                 # Provider config, resource group
│   ├── variables.tf            # Input variables
│   ├── outputs.tf              # Output values
│   ├── app_service.tf          # App Service Plan + Web App + Slots
│   ├── postgresql.tf           # PostgreSQL Flexible Server
│   ├── redis.tf                # Azure Cache for Redis
│   ├── keyvault.tf             # Key Vault + secrets
│   ├── openai.tf               # Azure OpenAI + deployments
│   ├── networking.tf           # VNet, subnets, NSGs, private endpoints
│   ├── dns.tf                  # Private DNS zones
│   ├── monitoring.tf           # Application Insights, Log Analytics
│   ├── identity.tf             # Managed identity role assignments
│   └── environments/
│       ├── dev.tfvars
│       ├── staging.tfvars
│       └── prod.tfvars
└── azure-pipelines/
    ├── ci.yml
    └── cd.yml
```

### Terraform in CI/CD

Infrastructure changes go through the same PR and review process as application code. A separate pipeline runs `terraform plan` on PR and `terraform apply` on merge to `main`.

---

## Disaster Recovery

### Recovery Objectives

| Parameter | Target |
|-----------|--------|
| RPO (data loss) | 5 minutes (PostgreSQL continuous WAL) |
| RTO (downtime) | < 1 hour |

### Failure Scenarios

| Scenario | Recovery |
|----------|----------|
| App Service instance failure | Auto-heal restarts. Multi-instance: immediate failover |
| Deployment breaks production | Slot swap back to previous version (< 1 minute) |
| Database corruption | Point-in-time restore from backup (< 1 hour) |
| Redis failure | Azure Cache auto-recovers. App reconnects automatically. Warm-up required for cache |
| Key Vault unavailable | App Service caches resolved secrets. Restart not possible until KV recovers |
| Azure OpenAI quota exceeded | Circuit breaker activates. Pending requests queued or rejected with user-facing message |
| SailPoint API outage | Requests queued via Taskiq. Users see "SailPoint unavailable, try later" message |
| Full region failure | Geo-redundant DB backup. Redeploy App Service in paired region |

### Recovery Testing

Monthly:
- Restore PostgreSQL to test server, validate data
- Simulate App Service failure, verify auto-heal
- Test slot swap rollback procedure
- Verify monitoring alerts fire correctly

Quarterly:
- Full DR drill: deploy from scratch in secondary region using Terraform
- Measure actual RTO against target

---

## Cost Management

### Monthly Cost Estimates

| Resource | SKU | Estimated Monthly Cost (USD) |
|----------|-----|------------------------------|
| App Service Plan (backend) | P2v3 (2 instances) | $500 |
| App Service Plan (worker) | P1v3 (1 instance) | $125 |
| PostgreSQL Flexible Server | D4ds_v5 + 128 GB | $350 |
| Azure Cache for Redis | Premium P1 (6 GB) | $340 |
| Azure OpenAI | 120K TPM @ ~$5/MTok | $200–800 (usage-dependent) |
| Key Vault | Standard | $5 |
| Static Web Apps | Standard | $9 |
| Application Insights | 5 GB/month ingest | $15 |
| VNet / Private Endpoints | 5 endpoints | $50 |
| **Total** | | **$1,600–2,200** |

Costs are approximate. Azure OpenAI cost varies significantly with usage volume.

### Cost Controls

- Set budget alerts at 80% and 100% of monthly budget in Azure Cost Management
- Use auto-scale with maximum instance limits to cap compute costs
- Monitor LLM token usage daily via the cost tracker in `services/llm/cost_tracker.py`
- Use `gpt-4o-mini` for classification and summarisation tasks (10x cheaper than `gpt-4o`)
- Review Azure Advisor recommendations monthly

---

## Environment Parity

### Environment Configuration

| Setting | Development | Staging | Production |
|---------|-------------|---------|------------|
| App Service SKU | B1 | P1v3 | P2v3 |
| Instances | 1 | 1 | 2 (min) |
| PostgreSQL SKU | Burstable B2ms | GP D2ds_v5 | GP D4ds_v5 |
| PostgreSQL HA | Disabled | Disabled | Zone-redundant |
| Redis SKU | Basic C1 | Premium P1 | Premium P1 |
| VNet / PE | Optional | Yes | Yes |
| Deployment slots | No | No | Yes |
| Custom domain | No | Optional | Yes |
| Auto-scale | No | No | Yes |
| Monitoring | Basic | Full | Full + Alerts |

Development uses cheaper SKUs but the **same architecture** — same code, same config structure, same service dependencies. No feature works in dev that fails in production because of infrastructure differences.

---

## Deployment Checklist

### Pre-Deployment

- [ ] All unit tests passing (CI green)
- [ ] Code reviewed and approved (PR merged)
- [ ] Database migrations tested against staging data
- [ ] Application settings verified in staging slot
- [ ] Key Vault secrets up to date
- [ ] Terraform plan reviewed (if infrastructure changes)
- [ ] Rollback plan documented (slot swap)

### Deployment

- [ ] Deploy to staging slot via CD pipeline
- [ ] Health check passes on staging URL
- [ ] Readiness check passes (DB, Redis, SailPoint connectivity)
- [ ] Smoke test critical paths (chat, access request, review)
- [ ] Swap staging → production
- [ ] Verify production health checks

### Post-Deployment

- [ ] Monitor error rate in Application Insights (15-minute window)
- [ ] Monitor response times (no regression)
- [ ] Verify WebSocket connections establish correctly
- [ ] Check SailPoint API connectivity
- [ ] Confirm LLM responses generating correctly
- [ ] Update deployment log (who, what, when)

### Rollback Trigger

Initiate rollback (slot swap) if any of:
- 5xx error rate > 5% within 10 minutes of swap
- Health check fails
- SailPoint API calls returning systematic errors
- LLM responses not generating (circuit breaker open)

Rollback command:
```bash
az webapp deployment slot swap \
  --name icarus-identity-chatbot \
  --resource-group rg-chatbot-prod \
  --slot staging \
  --target-slot production
```

---

## Migration from Bare-Metal (14-Deployment)

For teams migrating an existing bare-metal deployment to Azure:

| Bare-Metal Component | Azure Equivalent | Migration Notes |
|----------------------|------------------|-----------------|
| Ubuntu server | App Service Linux | No OS to manage |
| systemd services | App Service + WebJobs | Startup command replaces unit files |
| nginx reverse proxy | App Service built-in | TLS termination, HTTPS redirect included |
| Let's Encrypt | Managed Certificate | Auto-renewal included |
| PostgreSQL (self-hosted) | Flexible Server | pg_dump → restore. Update connection string |
| Redis (self-hosted) | Azure Cache for Redis | Use `rediss://` (TLS). Update connection string |
| `/opt/{app}/releases/` | Deployment slots | Slot swap replaces symlink swap |
| `.env` file | App Settings + Key Vault | Secrets move to Key Vault |
| logrotate + file logs | Application Insights | structlog JSON → App Insights automatic |
| UptimeRobot | Azure Monitor alerts | Built-in health check monitoring |
| pyenv + venv | App Service Python runtime | Platform manages Python version |
| Certbot renewal timer | Managed Certificate | Azure handles renewal |
