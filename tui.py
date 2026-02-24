"""
MVP TUI Client — Agent-First Terminal Interface.

Demonstrates the interactive terminal interface from 28-tui-architecture.md.
Uses mock data to simulate agent interactions without a running backend.

Usage:
    python tui.py
    python tui.py --debug
"""

from __future__ import annotations

import asyncio
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from rich.markdown import Markdown
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)


@dataclass
class AgentMessage:
    role: str
    content: str
    agent_name: str | None = None
    cost: float = 0.0
    tokens: int = 0
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None).strftime("%H:%M:%S"))


@dataclass
class ReasoningStep:
    step: int
    action: str
    detail: str
    cost: float = 0.0
    tokens: int = 0


@dataclass
class AgentDef:
    name: str
    description: str
    tier: str
    model: str
    tools: list[str]


MOCK_AGENTS = [
    AgentDef("code_reviewer", "Reviews code for bugs, style issues, and security vulnerabilities", "Specialist", "claude-sonnet-4", ["lint_runner", "code_search", "file_reader"]),
    AgentDef("report_writer", "Generates structured reports from data and research", "Specialist", "claude-sonnet-4", ["web_search", "data_query", "format_output"]),
    AgentDef("data_analyst", "Analyzes datasets, computes statistics, and surfaces insights", "Specialist", "claude-sonnet-4", ["data_query", "chart_gen", "stats_calc"]),
    AgentDef("search_worker", "Web search and result aggregation", "Worker", "claude-haiku-4.5", ["web_search"]),
    AgentDef("format_worker", "Data formatting and structuring", "Worker", "claude-haiku-4.5", ["format_output"]),
    AgentDef("summarize_worker", "Text summarization and compression", "Worker", "claude-haiku-4.5", ["summarize"]),
    AgentDef("orchestrator", "Routes requests to the appropriate specialist agent", "Thinker", "claude-opus-4", []),
]

MOCK_RESPONSES = {
    "review": [
        ReasoningStep(1, "tool_call", "lint_runner -> analyzing code structure...", 0.002, 180),
        ReasoningStep(2, "tool_call", "code_search -> checking for known vulnerability patterns...", 0.003, 250),
        ReasoningStep(3, "thinking", "Found 2 potential issues. Generating detailed review...", 0.008, 420),
    ],
    "report": [
        ReasoningStep(1, "delegate", "search_worker -> gathering recent data...", 0.001, 120),
        ReasoningStep(2, "delegate", "format_worker -> structuring results...", 0.001, 90),
        ReasoningStep(3, "thinking", "Compiling findings into report format...", 0.012, 650),
    ],
    "default": [
        ReasoningStep(1, "thinking", "Analyzing request and determining approach...", 0.005, 300),
        ReasoningStep(2, "thinking", "Generating response...", 0.010, 500),
    ],
}


class StatusBar(Static):
    """Persistent status bar showing session metrics."""

    session_cost: reactive[float] = reactive(0.0)
    session_tokens: reactive[int] = reactive(0)
    plans_running: reactive[int] = reactive(0)
    approvals_pending: reactive[int] = reactive(0)
    connected: reactive[bool] = reactive(True)

    def render(self) -> Text:
        conn = "[green]connected[/]" if self.connected else "[red]reconnecting[/]"
        approval_str = f" | [bold yellow]Approvals: {self.approvals_pending}[/]" if self.approvals_pending > 0 else ""
        return Text.from_markup(
            f" Session: [bold]${self.session_cost:.3f}[/] | "
            f"Tokens: [bold]{self.session_tokens:,}[/] | "
            f"Plans: [bold]{self.plans_running}[/] running"
            f"{approval_str} | "
            f"{conn}"
        )


class ChatLog(RichLog):
    """Chat message display with rich formatting."""


class AgentRegistryList(ListView):
    """Browseable list of available agents."""


class CostDashboard(Static):
    """Cost breakdown display."""

    def compose(self) -> ComposeResult:
        yield Static(self._render_costs(), id="cost-content")

    def _render_costs(self) -> str:
        return (
            "[bold]Cost Dashboard[/]\n"
            "─────────────────────────────────────\n"
            f"  Today       $4.50 / $50.00   [green]{'█' * 4}{'░' * 40}[/]  9%\n"
            f"  This week   $18.20\n"
            f"  This month  $42.80\n"
            "\n[bold]By Agent:[/]\n"
            "  code_reviewer    $12.30  (29%)\n"
            "  report_writer    $9.80   (23%)\n"
            "  data_analyst     $8.40   (20%)\n"
            "  orchestrator     $6.20   (15%)\n"
            "  workers          $6.10   (14%)\n"
            "\n[bold]By Model:[/]\n"
            "  claude-opus-4      $18.50  (43%)\n"
            "  claude-sonnet-4    $14.20  (33%)\n"
            "  claude-haiku-4.5   $10.10  (24%)\n"
        )


class AgentTUI(App):
    """MVP TUI Client for the Agentic AI Platform."""

    TITLE = "Agent TUI"
    SUB_TITLE = "AI-First Terminal Interface"

    CSS = """
    Screen {
        layout: vertical;
    }

    #chat-container {
        height: 1fr;
    }

    ChatLog {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    #chat-input {
        dock: bottom;
        margin: 0 0;
    }

    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }

    #registry-container {
        height: 1fr;
        padding: 1;
    }

    .agent-card {
        height: auto;
        margin: 0 0 1 0;
        padding: 1;
        border: solid $primary;
    }

    .agent-name {
        text-style: bold;
    }

    .agent-tier-thinker {
        color: $warning;
    }

    .agent-tier-specialist {
        color: $success;
    }

    .agent-tier-worker {
        color: $text-muted;
    }

    CostDashboard {
        height: 1fr;
        padding: 1 2;
    }

    #plan-monitor {
        height: 1fr;
        padding: 1 2;
    }

    TabbedContent {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+t", "new_chat", "New Chat"),
        Binding("ctrl+k", "kill_plan", "Kill Plan"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f1", "show_tab('chat')", "Chat", show=True),
        Binding("f2", "show_tab('registry')", "Registry", show=True),
        Binding("f3", "show_tab('costs')", "Costs", show=True),
        Binding("f4", "show_tab('plans')", "Plans", show=True),
    ]

    def __init__(self, debug: bool = False) -> None:
        super().__init__()
        self._debug = debug
        self._messages: list[AgentMessage] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Chat", id="chat"):
                with Vertical(id="chat-container"):
                    yield ChatLog(id="chat-log", highlight=True, markup=True)
                    yield Input(placeholder="Type a message... (Enter to send)", id="chat-input")
            with TabPane("Registry", id="registry"):
                with VerticalScroll(id="registry-container"):
                    for agent in MOCK_AGENTS:
                        tier_class = f"agent-tier-{agent.tier.lower()}"
                        yield Static(
                            f"[bold]{agent.name}[/] [{tier_class}]({agent.tier})[/]\n"
                            f"  {agent.description}\n"
                            f"  Model: {agent.model} | Tools: {', '.join(agent.tools) if agent.tools else 'none'}",
                            classes="agent-card",
                        )
            with TabPane("Costs", id="costs"):
                yield CostDashboard()
            with TabPane("Plans", id="plans"):
                yield Static(
                    "[bold]Plan Monitor[/]\n"
                    "─────────────────────────────────────────\n"
                    "  [green]✓[/] Step 1: researcher → gather data         $0.05\n"
                    "  [green]✓[/] Step 2: researcher → market analysis     $0.08\n"
                    "  [yellow]◌[/] Step 3: writer → draft report            $0.02...\n"
                    "  [dim]○[/] Step 4: reviewer → quality check          —\n"
                    "─────────────────────────────────────────\n"
                    "  Total: $0.15 / $1.00 budget | 3 of 4 steps\n"
                    "  Elapsed: 45s | Est. remaining: ~20s",
                    id="plan-monitor",
                )
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.write(Text.from_markup(
            "[bold]Welcome to Agent TUI[/]\n"
            "Type a message to interact with agents.\n"
            "Try: [italic]'review my code'[/], [italic]'write a report'[/], or anything else.\n"
            "─────────────────────────────────────────\n"
        ))

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_new_chat(self) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.clear()
        self._messages.clear()
        chat_log.write(Text.from_markup("[dim]── New chat session ──[/]\n"))

    def action_kill_plan(self) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.write(Text.from_markup("\n[bold red]⚡ Plan killed by user (Ctrl+K)[/]\n"))
        status = self.query_one(StatusBar)
        status.plans_running = max(0, status.plans_running - 1)

    @on(Input.Submitted, "#chat-input")
    def on_chat_submit(self, event: Input.Submitted) -> None:
        if not event.value.strip():
            return
        user_input = event.value.strip()
        event.input.value = ""
        self._handle_user_message(user_input)

    @work(thread=False)
    async def _handle_user_message(self, user_input: str) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        status = self.query_one(StatusBar)

        chat_log.write(Text.from_markup(f"\n[bold cyan]You:[/] {user_input}\n"))

        msg = AgentMessage(role="user", content=user_input)
        self._messages.append(msg)

        await asyncio.sleep(0.3)

        agent_name, steps = self._route_to_agent(user_input)
        chat_log.write(Text.from_markup(f"[dim]→ Routed to [bold]{agent_name}[/] agent[/]\n"))
        status.plans_running += 1

        await asyncio.sleep(0.2)

        total_cost = 0.0
        total_tokens = 0

        for step in steps:
            icon = {"tool_call": "🔧", "delegate": "📤", "thinking": "💭"}.get(step.action, "⚙️")
            chat_log.write(Text.from_markup(f"  {icon} {step.detail}"))
            total_cost += step.cost
            total_tokens += step.tokens
            status.session_cost += step.cost
            status.session_tokens += step.tokens
            delay = random.uniform(0.4, 1.2)
            await asyncio.sleep(delay)

        await asyncio.sleep(0.3)

        response_text = self._generate_response(user_input, agent_name)
        duration_ms = int(sum(random.uniform(400, 1200) for _ in steps))

        chat_log.write(Text.from_markup(
            f"\n[bold green]{agent_name}:[/] {response_text}\n"
        ))
        chat_log.write(Text.from_markup(
            f"[dim]  Cost: ${total_cost:.3f} | Tokens: {total_tokens:,} | Duration: {duration_ms}ms[/]\n"
        ))

        status.plans_running = max(0, status.plans_running - 1)

        agent_msg = AgentMessage(
            role="assistant",
            content=response_text,
            agent_name=agent_name,
            cost=total_cost,
            tokens=total_tokens,
            duration_ms=duration_ms,
        )
        self._messages.append(agent_msg)

    def _route_to_agent(self, user_input: str) -> tuple[str, list[ReasoningStep]]:
        text = user_input.lower()
        if any(kw in text for kw in ["review", "code", "bug", "security"]):
            return "code_reviewer", MOCK_RESPONSES["review"]
        if any(kw in text for kw in ["report", "write", "draft", "summarise", "summary"]):
            return "report_writer", MOCK_RESPONSES["report"]
        return "data_analyst", MOCK_RESPONSES["default"]

    def _generate_response(self, user_input: str, agent_name: str) -> str:
        if agent_name == "code_reviewer":
            return (
                "Found 2 issues:\n"
                "  1. **SQL injection** in `login()` — line 42. Use parameterized queries.\n"
                "  2. **Hardcoded secret** in `config()` — line 17. Move to environment variable."
            )
        if agent_name == "report_writer":
            return (
                "Report draft complete. Key findings:\n"
                "  - Market share grew 12% QoQ\n"
                "  - 3 new competitors entered the segment\n"
                "  - Recommendation: increase investment in product differentiation"
            )
        return (
            "Analysis complete. The dataset contains 1,247 records across 8 columns. "
            "Key insight: revenue distribution is bimodal with peaks at $2K and $8K."
        )


def main() -> None:
    debug = "--debug" in sys.argv
    app = AgentTUI(debug=debug)
    app.run()


if __name__ == "__main__":
    main()
