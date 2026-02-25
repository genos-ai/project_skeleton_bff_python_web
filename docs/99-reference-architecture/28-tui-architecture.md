# 28 - TUI Architecture (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-24*

## Changelog

- 1.0.0 (2026-02-24): Initial TUI architecture standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project needs:
- An interactive terminal interface for agent conversation and monitoring
- Real-time streaming of agent reasoning, tool calls, and cost tracking
- Session-based human-in-the-loop workflows (approvals, escalations)
- A power user interface that works over SSH and in low-bandwidth environments
- A browser-accessible terminal UI without building a separate React frontend

**Dependencies**: This module requires **07-frontend-architecture.md** (thin client principles) and benefits from **25-agentic-architecture.md** + **26-agentic-pydanticai.md** for agent integration patterns.

For command-based, one-shot operations (automation, scripting, CI/CD), use the CLI (Click) defined in 07-frontend-architecture.md. Adopt this module when the user needs a persistent, interactive session with real-time feedback.

---

## Context

The existing architecture defines two terminal-facing client types: the CLI (Click) for command-based operations and the Telegram bot for mobile chat. Neither serves the interactive, session-based workflow that an AI-first platform demands — where the user converses with agents, watches reasoning unfold in real-time, approves actions mid-execution, monitors multiple concurrent plans, and tracks cost accumulation live.

A TUI fills this gap. It is a persistent, interactive terminal application that stays open for the duration of a working session. It is keyboard-first, works over SSH, renders at 60 FPS, and — critically — the same codebase can be served in a browser via Textual Web with zero code changes.

For an AI-first platform where the primary user lives in the terminal, the TUI becomes the primary interface. The React web frontend (07-frontend-architecture.md) becomes optional — reserved for non-technical users or public-facing surfaces. The CLI remains essential for automation and scripting, but it is no longer the interactive human interface.

### How TUI differs from CLI

| Aspect | CLI (Click) | TUI (Textual) |
|--------|------------|---------------|
| Interaction model | Command → output → done | Persistent session, continuous interaction |
| State | Stateless — each invocation is independent | Stateful — session persists, context accumulates |
| Real-time | No — waits for command to complete | Yes — streams data as it arrives |
| Agent interaction | Trigger a task, poll for result | Converse with agents, watch them reason live |
| Human-in-the-loop | Not practical — would need to poll | Native — approval prompts appear instantly |
| Concurrent tasks | Run multiple commands in separate terminals | Tabs within one application |
| Use case | Automation, scripts, CI/CD, system admin | Interactive work, monitoring, agent sessions |

Both are needed. They serve different purposes and coexist.

---

## Technology Stack

### Framework: Textual

**Package:** `textual` (latest stable)

Textual is chosen because:
- Built by the Pydantic/Rich team — same ecosystem as the backend, CLI, and PydanticAI agents
- Python — no language boundary between TUI and backend
- React-inspired component hierarchy with CSS styling
- Reactive data binding — UI updates automatically when data changes
- Background workers keep the UI responsive during long operations
- 60 FPS rendering, 5-10x faster than curses
- Works over SSH
- **Textual Web** — same code runs in the browser via WebSocket with zero changes

### Supporting Libraries

| Concern | Solution |
|---------|----------|
| Framework | Textual |
| Rich text rendering | Rich (Textual dependency) |
| HTTP client | httpx (async) |
| WebSocket client | websockets or httpx-ws |
| Configuration | YAML + environment variables (same as CLI) |
| Authentication | API key stored in config file (same as CLI) |

### Textual Web

Textual Web serves the same TUI application in a browser via secure WebSocket. This eliminates the need for a React frontend for technical users:

- No separate codebase to maintain
- No TypeScript, no build step, no npm
- Same keyboard shortcuts, same layout, same behavior
- Accessible via URL — no installation needed for browser users
- Can run behind nginx (same deployment model as the backend)

Use Textual Web as the browser interface for internal/technical users. Build React only if you need a polished public-facing UI for non-technical users.

---

## Thin Client Mandate

The TUI follows the same thin client principles as all other clients per **01-core-principles.md P1/P2**:

- **No business logic** — all agent orchestration, tool execution, cost tracking happens in the backend
- **No data validation** beyond UI feedback — the backend validates everything
- **No local data persistence** — all state comes from the backend API, except ephemeral UI state (which tab is active, scroll position)
- **All state from backend APIs** — the TUI renders what the backend tells it

The TUI is a presentation layer. A sophisticated one — with real-time streaming, tabs, and interactive panels — but still just a presentation layer.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     TUI Application (Textual)                │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Tab 1   │  │  Tab 2   │  │  Tab 3   │  │  Tab N   │   │
│  │ Agent    │  │ Agent    │  │ Monitor  │  │ Memory   │   │
│  │ Session  │  │ Session  │  │ Dashboard│  │ Browser  │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │         │
│       └──────────────┴──────────────┴──────────────┘         │
│                              │                               │
│  ┌───────────────────────────┴────────────────────────────┐  │
│  │                    Status Bar                           │  │
│  │  Cost: $0.23 │ Tokens: 4.2K │ Plan: running │ Agents: 3│  │
│  └────────────────────────────────────────────────────────┘  │
│                              │                               │
│                    ┌─────────┴─────────┐                     │
│                    │    API Client      │                     │
│                    │  REST + WebSocket  │                     │
│                    └─────────┬─────────┘                     │
└──────────────────────────────┼───────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │   Backend (FastAPI)  │
                    │   X-Frontend-ID: tui │
                    └─────────────────────┘
```

### Connection Model

The TUI maintains two connections to the backend:

1. **REST (httpx)** — for request-response operations: submit tasks, approve/reject, query history, view costs, browse registry
2. **WebSocket** — for real-time streaming: agent reasoning steps, tool call results, cost updates, approval requests, plan progress

The WebSocket subscribes to events relevant to the current session. When the user switches tabs, subscriptions update. When the TUI disconnects, it reconnects with exponential backoff per **06-event-architecture.md**.

### X-Frontend-ID

The TUI sends `X-Frontend-ID: tui` with every request per **12-observability.md**. This enables:
- Log filtering by source (`logs/system.jsonl` with `source="tui"`)
- Per-frontend metrics in dashboards
- Debugging TUI-specific issues

---

## Core Panels

The TUI is organized into panels, composed into tabs. Each panel is a Textual Widget that subscribes to specific data streams.

### 1. Agent Chat Panel

The primary interaction surface. Conversational interface with the orchestrator.

**Layout:**
```
┌─────────────────────────────────────────────────┐
│  Agent Chat                                      │
│─────────────────────────────────────────────────│
│  You: Review this code for security issues       │
│                                                  │
│  ┌─ code_reviewer (thinking) ─────────────────┐ │
│  │ Analyzing code structure...                 │ │
│  │ 🔧 Tool: lint_runner → 3 issues found      │ │
│  │ 🔧 Tool: code_search → checking patterns   │ │
│  │ Generating review...                        │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  code_reviewer: Found 2 critical issues:         │
│  1. SQL injection in login() - line 42           │
│  2. Hardcoded secret in config() - line 17       │
│                                                  │
│  Cost: $0.03 │ Tokens: 2.1K │ Duration: 4.2s    │
│─────────────────────────────────────────────────│
│  > Type a message... (Ctrl+Enter to send)        │
└─────────────────────────────────────────────────┘
```

**Behavior:**
- User types a message and sends (Ctrl+Enter or configurable)
- Backend streams the agent's reasoning via WebSocket
- Tool calls appear inline as they happen
- Final response renders with full formatting (markdown via Rich)
- Cost/token/duration summary shown after each response
- Conversation history scrollable

### 2. Approval Panel

Appears when an agent requests human approval (Principle #6, #19 from 25).

```
┌─────────────────────────────────────────────────┐
│  ⚠ Approval Required                            │
│─────────────────────────────────────────────────│
│  Agent: code_deployer                            │
│  Action: Deploy to production                    │
│                                                  │
│  Context:                                        │
│  - Code review passed (2 issues fixed)           │
│  - Tests passing (47/47)                         │
│  - Branch: feature/auth-fix                      │
│                                                  │
│  [A]pprove    [R]eject    [V]iew details         │
└─────────────────────────────────────────────────┘
```

**Behavior:**
- Appears as an overlay or dedicated panel when `agents.task.awaiting_approval` event arrives
- Keyboard shortcuts for approve/reject (single keypress)
- Optionally shows full reasoning chain with [V]iew details
- After decision, panel dismisses and agent execution resumes

### 3. Plan Monitor Panel

Shows multi-step plan progress (Phase 2+).

```
┌─────────────────────────────────────────────────┐
│  Plan: Competitor Analysis Report                │
│─────────────────────────────────────────────────│
│  ✅ Step 1: researcher → gather data      $0.05  │
│  ✅ Step 2: researcher → market analysis  $0.08  │
│  🔄 Step 3: writer → draft report        $0.02… │
│  ⏳ Step 4: reviewer → quality check      —      │
│─────────────────────────────────────────────────│
│  Total: $0.15 / $1.00 budget │ 3 of 4 steps     │
│  Elapsed: 45s │ Est. remaining: ~20s             │
└─────────────────────────────────────────────────┘
```

**Behavior:**
- Steps update in real-time as agents complete work
- Cost accumulates visually
- Budget bar shows percentage consumed
- Click/Enter on a step to expand reasoning chain
- Kill plan with Ctrl+K

### 4. Status Bar

Persistent bar at the bottom of every view.

```
┌─────────────────────────────────────────────────────────────┐
│ Session: $0.23 │ Today: $4.50/$50 │ Plans: 2 running │ ⚠ 1 │
└─────────────────────────────────────────────────────────────┘
```

**Shows:**
- Session cost (accumulated since TUI opened)
- Daily cost vs budget
- Running plan count
- Pending approval count (with alert indicator)
- Connection status (connected/reconnecting)

### 5. Agent Registry Panel

Browse available agents and their capabilities.

```
┌─────────────────────────────────────────────────┐
│  Agent Registry                                  │
│─────────────────────────────────────────────────│
│  code_reviewer     Reviews code for bugs/security│
│  report_writer     Generates reports from data   │
│  data_analyst      Analyzes datasets             │
│  search_worker     Web search (worker tier)      │
│  format_worker     Data formatting (worker tier) │
│─────────────────────────────────────────────────│
│  Enter to view details │ / to search             │
└─────────────────────────────────────────────────┘
```

### 6. Memory Browser Panel (Phase 3+)

Browse and search agent memory entries.

```
┌─────────────────────────────────────────────────┐
│  Agent Memory                                    │
│─────────────────────────────────────────────────│
│  Search: code review patterns                    │
│─────────────────────────────────────────────────│
│  [0.94] code_reviewer - 2026-02-20              │
│    "async patterns preferred, avoid callbacks"   │
│  [0.87] code_reviewer - 2026-02-18              │
│    "SQL injection in login functions common"     │
│  [0.72] data_analyst - 2026-02-19               │
│    "revenue data usually in EMEA/APAC split"    │
│─────────────────────────────────────────────────│
│  Enter to view full entry │ D to delete          │
└─────────────────────────────────────────────────┘
```

### 7. Cost Dashboard Panel

Aggregated cost reporting.

```
┌─────────────────────────────────────────────────┐
│  Cost Dashboard                                  │
│─────────────────────────────────────────────────│
│  Today    $4.50 / $50.00  ████████░░░░░░  9%    │
│  This week $18.20                                │
│  This month $42.80                               │
│─────────────────────────────────────────────────│
│  By Agent:                                       │
│    code_reviewer    $12.30  (29%)                │
│    report_writer    $9.80   (23%)                │
│    data_analyst     $8.40   (20%)                │
│    orchestrator     $6.20   (15%)                │
│    workers          $6.10   (14%)                │
│─────────────────────────────────────────────────│
│  By Model:                                       │
│    claude-opus-4    $18.50  (43%)                │
│    claude-sonnet-4  $14.20  (33%)                │
│    claude-haiku-4.5 $10.10  (24%)                │
└─────────────────────────────────────────────────┘
```

---

## Tab Management

Tabs are the primary navigation mechanism. Each tab contains one or more panels.

### Default Tabs

| Tab | Key | Content |
|-----|-----|---------|
| Agent Chat | `1` | Chat panel + plan monitor (split) |
| Dashboard | `2` | Plan monitor + cost dashboard |
| Registry | `3` | Agent registry + tool list |
| Memory | `4` | Memory browser (Phase 3+) |
| History | `5` | Past task list with reasoning chains |

### Dynamic Tabs

- New agent sessions open in new tabs (`Ctrl+T`)
- Maximum configurable concurrent tabs (default: 10)
- Close tab with `Ctrl+W`
- Switch with `Alt+1` through `Alt+0` or `Tab`/`Shift+Tab`

### Tab Persistence

Tab state persists during the session but not across sessions. Tab content is reconstructed from backend API on reopen. Session history is in the backend, not the TUI.

---

## Keyboard Shortcuts

All shortcuts are configurable via YAML. Defaults follow vim conventions where applicable.

### Global

| Key | Action |
|-----|--------|
| `Ctrl+T` | New agent chat tab |
| `Ctrl+W` | Close current tab |
| `Alt+1..0` | Switch to tab 1-10 |
| `Ctrl+K` | Kill current plan (kill switch) |
| `Ctrl+Q` | Quit TUI |
| `Ctrl+/` | Command palette |
| `?` | Show help overlay |

### Chat Panel

| Key | Action |
|-----|--------|
| `Ctrl+Enter` | Send message |
| `Up` | Edit last message |
| `Escape` | Cancel current input |
| `Ctrl+L` | Clear chat history (visual only — history preserved in backend) |

### Approval Panel

| Key | Action |
|-----|--------|
| `A` | Approve |
| `R` | Reject |
| `V` | View details |

### Navigation

| Key | Action |
|-----|--------|
| `j/k` | Scroll down/up (vim) |
| `g/G` | Top/bottom |
| `/` | Search |
| `Enter` | Expand/select |
| `Escape` | Back/close |

---

## Module Structure

```
modules/tui/
├── __init__.py
├── app.py                      # Main Textual App class
├── config.py                   # TUI configuration loading
├── api_client.py               # REST + WebSocket client
├── screens/
│   ├── __init__.py
│   ├── main.py                 # Main screen with tab container
│   └── login.py                # API key entry (first run)
├── panels/
│   ├── __init__.py
│   ├── chat.py                 # Agent chat panel
│   ├── approval.py             # Approval overlay
│   ├── plan_monitor.py         # Plan progress panel
│   ├── status_bar.py           # Cost/status bar
│   ├── registry.py             # Agent registry browser
│   ├── memory.py               # Memory browser (Phase 3+)
│   ├── cost_dashboard.py       # Cost reporting
│   └── history.py              # Past task list
├── widgets/
│   ├── __init__.py
│   ├── agent_message.py        # Chat message rendering
│   ├── reasoning_step.py       # Reasoning chain step widget
│   ├── tool_call.py            # Tool call inline display
│   └── cost_badge.py           # Cost/token badge
└── styles/
    └── app.tcss                # Textual CSS stylesheet
```

### Configuration

```yaml
# config/settings/tui.yaml
tui:
  max_tabs: 10
  default_tabs:
    - chat
    - dashboard
    - registry

  keybindings:
    send_message: ctrl+enter
    kill_plan: ctrl+k
    quit: ctrl+q
    new_tab: ctrl+t

  display:
    show_reasoning_inline: true
    show_tool_calls_inline: true
    show_cost_per_message: true
    timestamp_format: "%H:%M:%S"

  connection:
    websocket_reconnect_delay: 1
    websocket_max_reconnect_delay: 30
    api_timeout: 30
```

---

## Entry Points

### Terminal

```bash
# Start TUI
python -m modules.tui

# Or via CLI
python cli.py --service tui
```

### Textual Web (Browser)

```bash
# Serve TUI in browser
textual serve modules.tui.app:TUIApp --port 8080

# Or behind nginx (production)
# upstream tui { server 127.0.0.1:8080; }
```

Textual Web serves the identical application in the browser. No code changes, no separate deployment. The same panels, same keyboard shortcuts, same real-time streaming.

---

## Real-Time Event Handling

### WebSocket Subscriptions

The TUI subscribes to agent events per **06-event-architecture.md**:

| Event | TUI Behavior |
|-------|-------------|
| `agents.task.created` | Add task to active plan monitor |
| `agents.task.completed` | Update plan step to completed, show cost |
| `agents.task.failed` | Show error in plan monitor, highlight in red |
| `agents.task.awaiting_approval` | Show approval panel overlay |
| `agents.task.cancelled` | Update plan step, show cancellation reason |
| `agents.plan.completed` | Show plan summary, update status bar |
| `agents.cost.warning` | Flash status bar warning |
| `agents.cost.exceeded` | Show budget exceeded alert |
| `agents.reasoning.step` | Stream reasoning step into chat panel |
| `agents.tool.call` | Show tool call inline in chat |
| `agents.tool.result` | Show tool result inline in chat |

### Streaming Agent Responses

Agent responses stream token-by-token via WebSocket. The chat panel renders incrementally using Textual's reactive data binding — the widget updates as data arrives, maintaining 60 FPS rendering.

For the reasoning chain: each reasoning step arrives as a discrete event. The chat panel renders steps as collapsible inline blocks — collapsed by default (showing "Thinking..."), expandable to show full reasoning.

---

## Testing

### Unit Testing

Test panels and widgets in isolation using Textual's pilot testing API:

```python
from textual.testing import AppTest

async def test_approval_panel_approve():
    app = AppTest(TUIApp)
    async with app.run_test() as pilot:
        # Simulate approval event
        app.post_message(ApprovalRequired(task_id="abc", action="deploy"))
        await pilot.pause()

        # Verify panel appeared
        assert app.query_one(ApprovalPanel).is_visible

        # Press approve key
        await pilot.press("a")
        await pilot.pause()

        # Verify panel dismissed
        assert not app.query_one(ApprovalPanel).is_visible
```

### Integration Testing

Test TUI against backend with mocked agents:

```python
async def test_chat_sends_to_backend(mock_backend):
    app = AppTest(TUIApp)
    async with app.run_test() as pilot:
        chat = app.query_one(ChatPanel)
        chat.input.value = "Review my code"
        await pilot.press("ctrl+enter")

        # Verify API call made
        assert mock_backend.last_request.path == "/api/v1/agents/chat"
        assert mock_backend.last_request.headers["X-Frontend-ID"] == "tui"
```

### Snapshot Testing

Textual supports SVG snapshots for visual regression testing — render the TUI to SVG and compare against baseline.

---

## Deployment

### Development

```bash
# Run directly
python -m modules.tui

# Run with debug logging
python -m modules.tui --debug
```

### Production (Terminal)

No special deployment — users SSH into the server and run the TUI. Or run locally with API pointing to remote backend.

### Production (Textual Web)

Deploy as a systemd service alongside the backend:

```ini
[Unit]
Description=TUI Web Interface
After=network.target

[Service]
Type=simple
User={app-user}
WorkingDirectory=/opt/{app-name}/current
EnvironmentFile=/opt/{app-name}/.env
ExecStart=/opt/{app-name}/venv/bin/textual serve modules.tui.app:TUIApp --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Nginx reverse proxy for HTTPS:

```nginx
location /tui/ {
    proxy_pass http://127.0.0.1:8080/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## Client Priority for AI-First Platforms

For platforms where the primary user is a developer/operator who lives in the terminal:

| Priority | Client | Purpose |
|----------|--------|---------|
| **Primary** | TUI (Textual) | Interactive agent sessions, monitoring, approvals, real-time |
| **Secondary** | CLI (Click) | Automation, scripting, system management, CI/CD |
| **Tertiary** | Textual Web | Same TUI served in browser — no separate build |
| **Optional** | React Web | Full visual UI for non-technical users (if ever needed) |
| **Optional** | Telegram | Mobile notifications, quick approvals on the go |

The React frontend (07-frontend-architecture.md) becomes optional. Textual Web covers the browser case with zero additional code. Build React only when you need a polished public-facing UI for users who are not comfortable in a terminal.

---

## Adoption Checklist

When adopting this module:

- [ ] Install Textual (`pip install textual`)
- [ ] Create `modules/tui/` directory structure
- [ ] Implement main App class with tab container
- [ ] Implement API client (REST + WebSocket)
- [ ] Implement chat panel with message streaming
- [ ] Implement status bar with cost tracking
- [ ] Implement approval panel overlay
- [ ] Implement plan monitor panel
- [ ] Configure `X-Frontend-ID: tui` on all API calls
- [ ] Add `tui` to log source list in `12-observability.md`
- [ ] Create TUI configuration in `config/settings/tui.yaml`
- [ ] Add CLI entry point (`--action tui`)
- [ ] Write panel unit tests with Textual pilot API
- [ ] Test WebSocket reconnection behavior
- [ ] Set up Textual Web for browser access (if needed)

---

## Related Documentation

- [07-frontend-architecture.md](07-frontend-architecture.md) — Thin client principles, CLI (Click), Web (React)
- [25-agentic-architecture.md](25-agentic-architecture.md) — Agent concepts, human-in-the-loop, cost tracking, reasoning chains
- [26-agentic-pydanticai.md](26-agentic-pydanticai.md) — PydanticAI implementation, API endpoints, event types
- [06-event-architecture.md](06-event-architecture.md) — WebSocket patterns, event types
- [12-observability.md](12-observability.md) — X-Frontend-ID, log sources
- [01-core-principles.md](01-core-principles.md) — Thin client mandate (P1, P2)
