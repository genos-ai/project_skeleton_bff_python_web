# Building an AI chatbot for SailPoint IdentityNow on Azure

**An LLM-powered chatbot can transform SailPoint identity governance from portal-driven clicks into natural language conversations—but no production-ready implementation exists today.** This gap is significant: competitors like Omada (Javi) and Saviynt (SaviAI) have shipped conversational AI for IGA, while SailPoint's own Harbor Pilot targets administrators, not end users. The architecture below combines LangGraph for orchestration, SailPoint's v3 APIs and Python SDK for identity operations, and Azure App Service for deployment, with defense-in-depth security to ensure the chatbot can never bypass governance controls. SailPoint's comprehensive API surface—access requests, certifications, search, and event triggers—provides everything needed to build both use cases: natural language access requests and simplified access reviews.

## SailPoint IdentityNow API surface provides full coverage

SailPoint's v3 and beta APIs expose every operation the chatbot needs. The base URL follows the pattern `https://{tenant}.api.identitynow.com`, with authentication via **OAuth 2.0 client credentials** (`POST /oauth/token` returning short-lived JWTs expiring in ~12.5 minutes) or Personal Access Tokens that inherit the creating user's permissions.

### Access request APIs

The core endpoint is `POST /v3/access-requests`, which accepts a JSON body specifying `requestedFor` (array of identity IDs), `requestType` (`GRANT_ACCESS` or `REVOKE_ACCESS`), and `requestedItems` containing the item `type` (`ACCESS_PROFILE`, `ROLE`, or `ENTITLEMENT`), `id`, and `comment`. Limits are **25 entitlements and 10 recipients per request**. The response is `202 Accepted`—asynchronous processing. Supporting endpoints include `GET /v3/access-request-status` for tracking, `GET /v3/access-request-approvals/pending` for listing pending approvals, and `POST /v3/access-request-approvals/{id}/approve` or `/reject` for acting on them. To discover requestable items, use `GET /v3/access-profiles?filters=requestable eq true`, `GET /v3/roles?filters=requestable eq true`, or the powerful `POST /v3/search` endpoint which supports elastic search across identities, access profiles, entitlements, and roles.

### Certification campaign APIs

For access reviews, the key endpoints are:

- **`GET /v3/certifications`** — lists all certifications assigned to a reviewer
- **`GET /v3/certifications/{id}/access-review-items`** — retrieves individual items within a certification
- **`POST /v3/certifications/{id}/decide`** — submits decisions (supports bulk operations with an array of `{id, decision, comments}` where decision is `APPROVE` or `REVOKE`)
- **`POST /v3/certifications/{id}/sign-off`** — finalizes the certification
- **`POST /beta/certifications/{id}/reassign-async`** — reassigns up to 500 items to another reviewer

Campaign management endpoints (`GET/POST /v3/campaigns`) require `ORG_ADMIN` or `CERT_ADMIN` roles and support creating campaigns with IAI (Identity AI) recommendations enabled.

### Python SDK and event triggers

The official **`sailpoint` package** (installed via `pip install sailpoint`) is auto-generated from OpenAPI specs and mirrors every v3 and beta endpoint. Key classes include `sailpoint.v3.AccessRequestsApi` (with `create_access_request()`), `sailpoint.v3.CertificationsApi` (with `make_identity_decision()`), and `sailpoint.v3.SearchApi` (with `search_post()`). A built-in `Paginator` utility handles pagination across large result sets. The SDK reads configuration from environment variables (`SAIL_BASE_URL`, `SAIL_CLIENT_ID`, `SAIL_CLIENT_SECRET`).

SailPoint's **event trigger system** provides real-time notifications via webhooks or AWS EventBridge. Critical triggers for the chatbot include `idn:access-requested`, `idn:campaign-activated`, `idn:campaign-ended`, and `idn:certification-signed-off`. Subscriptions are managed via `POST /beta/trigger-subscriptions` with support for HTTP authentication, JSONPath filtering, and response deadlines for request-response triggers like `idn:access-request-dynamic-approver`.

## LangGraph orchestration with human-in-the-loop gating

The chatbot architecture centers on an LLM agent that understands natural language intent and maps it to SailPoint API tool calls, with mandatory human confirmation before any state-changing operation.

### Why LangGraph over alternatives

Three orchestration approaches were evaluated. **LangGraph** (LangChain's agent framework) is recommended for this use case because of its built-in `interrupt()` pattern for human-in-the-loop workflows—critical for gating access request submissions and certification decisions. It provides stateful graph execution with checkpointing to PostgreSQL or Redis, handles the complete tool-calling loop, and supports both Azure OpenAI and Anthropic Claude. **Semantic Kernel** is a strong alternative for teams deeply invested in the Microsoft ecosystem—it auto-generates tool schemas from Python type annotations and handles function calling automatically, but lacks LangGraph's native interrupt/resume pattern. **Direct SDK integration** (calling the `openai` or `anthropic` libraries directly) offers maximum control with minimal dependencies but requires implementing the tool loop, state management, and confirmation workflows manually.

### Tool definitions and function calling

The LLM interacts with SailPoint through defined tools. For Azure OpenAI, tools use the `tools` parameter with `"strict": True` for guaranteed schema compliance. For Anthropic Claude, the equivalent `tools` parameter uses `input_schema`. Both support parallel tool calling and multi-step reasoning. The essential tool set for the chatbot includes:

- **`search_identities`** — queries SailPoint's search API to resolve users by name, email, or employee ID
- **`search_access_items`** — finds requestable access profiles, roles, or entitlements matching a natural language description
- **`submit_access_request`** — calls `POST /v3/access-requests` after confirmation
- **`get_pending_reviews`** — retrieves certification items assigned to the authenticated user
- **`decide_certification_item`** — approves or revokes individual items via `POST /v3/certifications/{id}/decide`
- **`check_request_status`** — queries `GET /v3/access-request-status` for request tracking

The core flow works as follows: user sends a message → FastAPI backend passes it to the LangGraph agent → LLM determines intent and selects tools → read-only tools execute immediately → write operations trigger a LangGraph `interrupt()` that pauses execution and returns a confirmation prompt to the user → user confirms via structured UI element → `Command(resume="approve")` resumes the graph and executes the SailPoint API call.

```
┌─────────────────────────────────────────────────────┐
│            FastAPI + WebSocket Server                │
│  ┌───────────────────────────────────────────────┐  │
│  │          LangGraph Agent Orchestrator          │  │
│  │                                                │  │
│  │  [Agent Node] → [Tool Router] → [Tool Node]   │  │
│  │       ↑              │               │         │  │
│  │       └──────────────┘    ┌──────────┘         │  │
│  │                           ↓                    │  │
│  │              [Human Review Node]               │  │
│  │              (interrupt/resume)                 │  │
│  └───────────────────┬───────────────────────────┘  │
│                      │                               │
│  ┌───────────────────▼───────────────────────────┐  │
│  │      SailPoint API Client (async, httpx)       │  │
│  │  OAuth2 token manager · retry with backoff     │  │
│  └───────────────────┬───────────────────────────┘  │
└──────────────────────┼───────────────────────────────┘
                       │ HTTPS
         ┌─────────────▼──────────────┐
         │  SailPoint IdentityNow     │
         │  /v3/access-requests       │
         │  /v3/certifications        │
         │  /v3/search                │
         └────────────────────────────┘
```

### Conversation state and session management

LangGraph's built-in checkpointing handles conversation state persistence. For production, use `PostgresSaver` backed by Azure Database for PostgreSQL, keyed by `thread_id` (one per user session). This stores the full message history, pending tool calls, and interrupt state, enabling the multi-turn flows required for access requests (identify user → search items → select → confirm → submit) and access reviews (load items → present summaries → collect decisions → submit → sign off). Redis serves as the session cache for fast lookups, with a **TTL of 1 hour** for inactive conversations.

## Simplifying access reviews through intelligent pre-processing

Access certification campaigns are where the chatbot delivers the most transformative value. Traditional reviews present managers with hundreds of items, leading to **"rubber-stamping"**—approving everything without genuine review. The chatbot addresses this through a three-tier processing model.

### Risk-based pre-filtering

Before presenting items to the reviewer, the chatbot pre-processes certification items through a scoring function that evaluates multiple risk signals: whether the entitlement grants privileged access (+0.4 risk), whether it hasn't been used in 90+ days (+0.2), whether it creates a Separation of Duties violation (+0.5), and whether it falls outside the user's peer group access pattern (+0.15). Items scoring below **0.3** with a SailPoint AI recommendation of "APPROVE" are candidates for bulk auto-approval. Items scoring above **0.7** or flagged for SoD violations are escalated for detailed human review with LLM-generated explanations.

SailPoint's own AI Services already provide recommendation engine data (thumbs-up/thumbs-down based on peer group analysis) accessible through the certification API responses. The chatbot should consume these recommendations as an input signal, complementing them with additional risk scoring rather than duplicating the capability.

### LLM-powered item summarization

For items requiring human attention, the chatbot uses the LLM to translate technical entitlement names into plain language. For example, instead of presenting "CN=APP-SAP-FI-POST,OU=Groups,DC=corp", the chatbot explains: "This grants the ability to post financial journal entries in SAP. **12 of 15 peers in the Finance Analyst role have this access.** Last used 3 days ago. Recommendation: Approve." SailPoint's new GenAI-powered entitlement descriptions feature (using Claude via Amazon Bedrock) addresses the same problem within the ISC UI—the chatbot extends this capability to Teams and Slack conversations.

### The exception-based review workflow

The chatbot presents reviews as a conversation: "You have **47 access items** to review for your team. I've analyzed them: **38 are low-risk and match peer group patterns**—shall I approve those? **6 items need your attention** (3 unused accounts, 2 SoD conflicts, 1 privileged escalation). **3 items I'd recommend revoking.** Let's start with the items that need attention." This transforms a 47-item checkbox exercise into a focused review of 9 exceptions, with the reviewer maintaining full control over the final decisions.

## Azure deployment architecture and infrastructure

### Azure App Service as the primary compute platform

**Azure App Service (Premium v3 tier)** is the recommended deployment target. It provides native Python support on Linux, built-in WebSocket support for streaming LLM responses, VNet integration for network isolation, deployment slots for blue-green deployments, and system-assigned managed identities. Deploy as a FastAPI application with the startup command `gunicorn -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 main:app`. Azure Container Apps is a viable alternative for teams wanting scale-to-zero cost savings or microservices architecture, but adds container management complexity. Azure Functions is **not recommended** as the primary backend due to the 230-second HTTP timeout limit and cold-start issues that degrade conversational UX.

### Microsoft Teams integration via Agents SDK

The Bot Framework SDK was **retired in December 2025**. The replacement is the **Microsoft 365 Agents SDK** (`microsoft-agents` packages on PyPI). The Agents SDK provides `TeamsActivityHandler` for handling Teams messages, `microsoft-agents-authentication-msal` for SSO, and support for Adaptive Cards for structured confirmation dialogs. The VS Code "Microsoft 365 Agents Toolkit" extension provides scaffolding templates. For custom web chat interfaces, the DirectLine API remains supported, with the DirectLine App Service Extension available for VNet isolation.

### Azure OpenAI integration

Configure the `openai` Python library to use Azure OpenAI by setting `base_url` to `https://{resource}.openai.azure.com/openai/v1/`. **Use Entra ID authentication via managed identity** rather than API keys—assign the `Cognitive Services OpenAI User` role to the App Service's managed identity, then use `DefaultAzureCredential` with `get_bearer_token_provider` for automatic token management. Deploy GPT-4o (or gpt-4.1 when available) with sufficient Tokens-Per-Minute quota (**120K+ TPM recommended** for production workloads). Implement retry logic with exponential backoff for 429 responses.

### Security infrastructure

The security architecture follows a **three-subnet VNet model**: an application subnet for App Service VNet integration (outbound traffic), a private endpoint subnet for Azure OpenAI and Key Vault (traffic stays on Azure backbone), and a management subnet with Azure Bastion for administrative access. Store all SailPoint credentials (client ID, client secret) in **Azure Key Vault** with RBAC authorization enabled—the App Service managed identity gets only the `Key Vault Secrets User` role (not Officer). App Service references secrets directly via Key Vault references in app settings: `@Microsoft.KeyVault(VaultName=chatbot-kv;SecretName=sailpoint-client-secret)`.

User authentication flows through **Entra ID**: the chatbot authenticates the user via MSAL, extracts their UPN or email from the JWT claims, and resolves their SailPoint identity via `POST /v3/search` with an identity query. This mapping ensures every SailPoint API call is scoped to the authenticated user's permissions.

## No existing SailPoint chatbot—but the market validates the approach

A thorough search confirms **no open-source AI chatbot for SailPoint exists**. SailPoint's own ecosystem offers command-driven Slack and Teams bots (slash commands like `/sailpoint create`) and Harbor Pilot (an admin-focused AI for documentation Q&A and workflow generation on Amazon Bedrock). Neither provides end-user natural language access requests or conversational access reviews.

The competitive landscape strongly validates this architecture. **Omada's "Javi" AI assistant** (GA June 2025) is the closest analog—built on Microsoft Semantic Kernel, integrated with Teams and Slack, supporting natural language access requests and approvals. **Saviynt launched an MCP Server** enabling any LLM to query its identity cloud via natural language. ConductorOne ships AI-powered Slack integration for access workflows. KuppingerCole analyst Martin Kuppinger has endorsed conversational IGA as a key innovation vector, and Gartner predicts **50% of customer service organizations will adopt AI agents by 2028**.

SailPoint's existing AI Services (recommendation engine for certifications, access modeling for role mining, GenAI entitlement descriptions) are complementary, not competitive. The chatbot consumes SailPoint's recommendation data and risk scores as inputs while providing a conversational interface that SailPoint's platform currently lacks for end users.

## Security architecture demands defense-in-depth

The highest-risk aspect of this system is that an LLM—inherently unpredictable—sits between users and an identity governance platform that controls access to enterprise resources. The security model must follow one absolute principle: **the LLM never enforces access controls; deterministic code does**.

### Authorization enforcement

Every SailPoint API call passes through a server-side authorization middleware that validates the authenticated user owns the target resource (their own access reviews, their own requests) before execution. The LLM selects tools and parameters; the validation layer rejects calls that violate authorization rules regardless of what the LLM requested. User roles in the chatbot (regular user, reviewer, admin) are derived from Entra ID app roles and SailPoint identity attributes—never from conversation context.

### Prompt injection mitigation

Prompt injection is the **OWASP #1 risk for LLM applications in 2025**. The chatbot mitigates this through layered defenses: input validation with pattern detection before messages reach the LLM; strict system prompts constraining the model to identity governance tasks; output validation ensuring tool call parameters match expected schemas and user permissions; sandboxed tool execution with allowlisted operations per user role; and structured UI confirmation (buttons, not free-text) for all state-changing operations. The chatbot should never pass LLM output directly to SailPoint APIs without deterministic parameter validation.

### Audit logging and compliance

Every interaction generates audit records at two levels: the chatbot application layer (user prompts, LLM responses, tool calls, confirmations) logged to Azure Application Insights with correlation IDs, and the SailPoint layer (access requests, certification decisions) captured in SailPoint's built-in audit trail. Both streams should feed into a SIEM via Azure Event Hubs. For **SOX compliance**, the critical requirement is that AI-assisted certification decisions maintain a complete evidence chain: the chatbot's recommendation, the human reviewer's explicit decision, and the executed action—all linked by correlation IDs and stored in immutable, append-only storage. Grant Thornton's 2025 SOX guidance positions AI as a "co-pilot augmenting human judgment, not replacing it."

### Data privacy with LLMs

For Azure OpenAI, customer data is **not used for model training**, and enterprise customers can request Zero Data Retention (ZDR) so prompts and responses are not retained beyond in-memory processing. Anthropic's Commercial API terms similarly exclude customer data from training, with default 30-day retention (moving to 7 days) and ZDR available under security addendum. Both platforms offer SOC 2 Type II certification. Data minimization is essential: send only the fields needed for the current interaction (entitlement names, not full identity profiles), use reference IDs instead of PII where possible, and never send passwords or tokens to the LLM.

## Implementation roadmap

The following four-phase roadmap targets production readiness in **16–20 weeks**, assuming a team of 2–3 engineers.

**Phase 1 — Foundation (Weeks 1–4):** Stand up Azure infrastructure with Terraform (App Service, Key Vault, Azure OpenAI, VNet with private endpoints). Implement SailPoint API client with OAuth2 token management and retry logic. Build the basic LangGraph agent with tool definitions for `search_identities`, `search_access_items`, and `check_request_status` (read-only operations only). Validate end-to-end flow: user message → LLM intent → SailPoint search → natural language response.

**Phase 2 — Access requests with HITL (Weeks 5–8):** Add `submit_access_request` and `approve_request` tools with LangGraph interrupt/resume confirmation gate. Implement Entra ID user authentication and SailPoint identity resolution. Build the multi-turn access request conversation flow (identify → search → select → confirm → submit → track). Deploy to staging with integration tests against a SailPoint sandbox tenant.

**Phase 3 — Access reviews and intelligence (Weeks 9–14):** Implement certification item retrieval and risk-based pre-filtering. Build the LLM summarization pipeline for entitlement descriptions. Create the exception-based review workflow with bulk approve for low-risk items. Integrate SailPoint AI recommendation data as scoring input. Add event trigger subscriptions for `idn:campaign-activated` to proactively notify reviewers.

**Phase 4 — Channels, hardening, and production (Weeks 15–20):** Integrate with Microsoft Teams via the M365 Agents SDK. Implement comprehensive audit logging with Application Insights and SIEM forwarding. Conduct prompt injection red-team testing with IGA-specific attack scenarios. Complete SOX compliance documentation (AI inventory, risk assessment, evidence chain design). Performance test under load and deploy to production with deployment slots for zero-downtime releases.

## Conclusion

This architecture fills a validated market gap—SailPoint's 40,000+ customers have no AI-powered conversational interface for end-user identity governance. The technical foundation is strong: SailPoint's v3 APIs cover every needed operation, the Python SDK wraps them cleanly, LangGraph provides production-grade orchestration with human-in-the-loop gating, and Azure App Service offers a straightforward deployment path with enterprise security. The critical insight is that **the LLM is an interface layer, not a decision-maker**—it translates natural language to API calls and summarizes technical data for humans, while deterministic code enforces every authorization check, validates every parameter, and logs every action. The access review simplification use case alone—reducing a 200-item rubber-stamp exercise to a focused review of 15 exceptions—justifies the investment, particularly for organizations facing SOX audit pressure on certification quality.