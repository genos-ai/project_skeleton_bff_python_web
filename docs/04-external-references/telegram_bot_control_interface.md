# Telegram bot as a trading platform control interface

**aiogram v3 running in webhook mode inside a FastAPI application is the optimal architecture for a Telegram-controlled trading platform**, providing native event loop sharing, router-based handler organization, and built-in finite state machines for multi-step trade flows. This approach treats the Telegram bot as a thin Backend-for-Frontend (BFF) client that translates user interactions into API calls against your existing FastAPI service layer — keeping all business logic centralized and the attack surface minimal. With live capital at risk, every design decision below prioritizes defense-in-depth: user ID whitelisting, HMAC-signed time-limited confirmations, circuit breakers, and an independent kill switch process that can halt trading even if the bot itself fails.

This report covers framework selection, integration patterns, security architecture, core functionality implementation, real-world references, and operational considerations — with specific code patterns throughout.

---

## Why aiogram v3 is the right framework for FastAPI

Three mature Python libraries compete for this use case: **aiogram v3**, **python-telegram-bot (PTB) v20+**, and **Telethon**. For a FastAPI-based trading platform, aiogram v3 wins decisively on architectural fit.

The critical differentiator is event loop compatibility. aiogram v3 exposes `dp.feed_update(bot, update)`, which processes Telegram updates synchronously within FastAPI's request-response cycle on the **same asyncio event loop** managed by Uvicorn. PTB v20+, despite its async rewrite, was designed to own the event loop — its `run_polling()` and `run_webhook()` methods block, requiring awkward workarounds (setting `updater=None`, manually managing lifecycle via `lifespan`). Telethon uses MTProto rather than the Bot API, making it a poor fit for standard bot interactions but useful for advanced Telegram features.

| Feature | aiogram v3 | python-telegram-bot v20+ | Telethon |
|---|---|---|---|
| FastAPI integration | ★★★★★ Native via `feed_update` | ★★★☆☆ Requires workarounds | ★★☆☆☆ Background task needed |
| FSM / Conversations | Built-in `StatesGroup` + `aiogram-dialog` | `ConversationHandler` (fragile with manual feeding) | No built-in support |
| Middleware system | Two-scope (outer/inner), injectable | Application-level only | Event handlers |
| Router architecture | Nested router tree (mirrors FastAPI) | Handler groups | Event decorators |
| Callback data | Type-safe `CallbackData` factory | Manual string parsing | Basic support |
| Maintenance | Active, **v3.25+**, Python 3.10+ | Active, **v22.6**, 26k+ stars | Active, 10k+ stars |

aiogram v3's router architecture mirrors FastAPI's own `APIRouter` pattern, enabling clean separation of trading handlers, settings handlers, and monitoring handlers into distinct modules. Its middleware system supports two scopes — outer middleware runs on every update (ideal for auth checks), while inner middleware runs after filters pass (ideal for rate limiting). The `CallbackData` factory provides type-safe inline keyboard handling where trade parameters (symbol, amount, action) are encoded and decoded with Pydantic-style validation rather than fragile string splitting.

---

## Integration architecture: webhook mode on a shared ASGI server

The canonical pattern runs aiogram's dispatcher inside FastAPI, sharing the same Uvicorn process and HTTPS endpoint. This eliminates the need for separate processes and simplifies deployment on a single VPS.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(trading_router)
dp.include_router(monitoring_router)

WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET_PATH}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.set_webhook(
        url=f"https://yourdomain.com{WEBHOOK_PATH}",
        secret_token=WEBHOOK_SECRET_TOKEN,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
    )
    yield
    await bot.delete_webhook()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request) -> Response:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not hmac.compare_digest(secret or "", WEBHOOK_SECRET_TOKEN):
        return Response(status_code=403)
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return Response(status_code=200)
```

**Webhook mode is strongly preferred over long-polling for VPS deployment.** Webhooks deliver lower latency (Telegram pushes instantly rather than polling every N seconds), consume fewer resources (no constant HTTP requests to Telegram), and coexist naturally with your existing FastAPI HTTPS endpoint. Long-polling is acceptable only during local development where you lack a public HTTPS endpoint. Several production-ready templates exist on GitHub: `bralbral/fastapi_aiogram_template` (Docker-ready, tested on Ubuntu 22.04), `nessshon/aiogram-starlette-template` (includes Nginx, Certbot, Redis), and the `aiogram-fastapi-server` PyPI package as a drop-in webhook handler.

The recommended project structure keeps the bot as a pure presentation layer:

```
app/
├── main.py                 # FastAPI app + webhook endpoint
├── services/               # Business logic (trading, portfolio, risk)
├── api/v1/                 # REST API routes (used by web UI, other clients)
├── bot/
│   ├── handlers/           # Telegram command handlers (thin: parse → call service → format)
│   ├── middlewares/         # Auth, rate limiting, logging
│   ├── keyboards/          # Inline keyboard builders
│   ├── states/             # FSM state definitions
│   └── callbacks/          # CallbackData factories
└── models/                 # Shared Pydantic/SQLAlchemy models
```

The bot layer translates Telegram interactions into calls to the same `services/` layer used by REST API routes. It handles presentation logic only — formatting, keyboards, pagination, FSM flow control. **All trading logic, risk checks, and order validation live in `services/`**, never in bot handlers.

---

## Security architecture for live capital protection

With real money at risk, security requires defense-in-depth across every layer. The following measures are ordered by criticality.

### Authentication and authorization via user ID whitelisting

Telegram user IDs are **immutable integers** tied to accounts and cannot be spoofed within the Telegram API. This is your primary authentication gate. Implement it as aiogram outer middleware so it runs before any handler:

```python
class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user_id = event.from_user.id
        if user_id not in AUTHORIZED_USERS:
            logger.warning(f"Unauthorized access: user_id={user_id}")
            return  # Silently drop — don't reveal bot exists
        data["user_role"] = USER_ROLES.get(user_id, "viewer")
        return await handler(event, data)
```

Freqtrade's production Telegram module uses exactly this pattern — an `@authorized_only` decorator wrapping every command handler that compares incoming `chat_id` against configuration. Define at least three roles: **admin** (kill switch, deploy, config changes), **trader** (buy/sell within limits), and **viewer** (read-only status commands). Restrict trade commands to private chats only by checking `message.chat.type == "private"`.

### Multi-factor trade confirmation with time-limited tokens

Every trade command should follow a two-step flow: command → preview with confirmation keyboard → execute. Confirmation tokens must be **HMAC-signed, time-limited, and single-use**:

```python
def generate_confirmation_token(user_id: int, action: str, params: dict) -> str:
    nonce = secrets.token_hex(8)
    timestamp = int(time.time())
    payload = f"{user_id}:{action}:{json.dumps(params, sort_keys=True)}:{timestamp}:{nonce}"
    signature = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{timestamp}:{nonce}:{signature}"
```

Tokens expire after **30 seconds** and are marked as used in Redis immediately upon processing, preventing replay attacks. For high-value trades, add an optional TOTP factor via `pyotp`. Enforce **maximum trade size limits** at both the bot level and BFF level (defense in depth), plus per-user cooldown periods between trades stored in Redis.

### Bot token and webhook security

The bot token grants **full control** — a compromised token lets attackers read all message history, send messages to any chat, and impersonate the bot. Real-world incidents include malware using exposed tokens to exfiltrate chat histories (documented by Forcepoint) and a trading platform's support bot being hijacked via a hardcoded token in a public repository, enabling phishing attacks against 397+ users.

Store tokens exclusively in environment variables or a secrets manager (HashiCorp Vault, Docker secrets). Run `trufflehog` or GitGuardian's `ggshield` as pre-commit hooks. **Rotate tokens proactively every 3-6 months** via BotFather's `/revoke` command, which instantly invalidates the old token. For webhook security, set Telegram's `secret_token` parameter and validate the `X-Telegram-Bot-Api-Secret-Token` header on every request. Restrict your webhook endpoint at the firewall level to Telegram's IP ranges: **`149.154.160.0/20`** and **`91.108.4.0/22`**.

### Command injection prevention and input validation

**Never** use `eval()`, `exec()`, or `os.system()` with any user input. Parse trade commands with strict regex validation against a whitelist of known symbols:

```python
VALID_SYMBOLS = {"BTC", "ETH", "SOL", "AVAX"}
match = re.match(r'^/(buy|sell)\s+([A-Z]{2,10})\s+(\d+\.?\d*)$', text.strip())
if not match or match.group(2) not in VALID_SYMBOLS:
    raise ValueError("Invalid command")
```

Use Pydantic models with `Field(pattern=...)` validators at the BFF API layer as a second validation gate. If subprocess calls are unavoidable for system monitoring, always use `subprocess.run([cmd, arg1, arg2], shell=False)` with `shlex.quote()`.

### Rate limiting, API security, and audit logging

Implement **Redis-based per-user rate limiting** with separate thresholds: 5 trades per minute, 30 general commands per minute. Libraries like `slowapi` or `fastapi-limiter` integrate directly with FastAPI. Between the bot and BFF API, use **JWT or HMAC-signed requests** with timestamp validation (reject requests older than 30 seconds) to prevent replay attacks on the internal API surface.

Log every command with structured JSON (via `structlog` or `loguru`): user ID, timestamp, full command text, result, and update_id. Send real-time alerts to a separate admin Telegram channel for unauthorized access attempts, rate limit breaches, and kill switch activations.

### Kill switch and emergency stop

The kill switch is the most critical safety mechanism. Implement it as a **Redis flag** checked before every trade execution:

```python
@require_auth(min_role="admin")
async def kill_switch(message, state):
    redis_client.set("trading:kill_switch", json.dumps({
        "active": True, "reason": reason, "timestamp": time.time()
    }))
    await cancel_all_open_orders()  # Immediately cancel via exchange API
    await alert_admin("🛑 KILL SWITCH ACTIVATED")
```

Add **automatic kill switches** that trigger on drawdown limits (daily loss exceeding threshold), error rate spikes, or consecutive failed orders. Critically, run an **independent monitoring process** as a separate systemd service that polls exchange APIs directly and can activate the kill switch via Redis even if the main bot process is unresponsive. Configure exchange API keys with **trading permissions only — never enable withdrawals** — and IP-whitelist them to your VPS.

### VPS hardening checklist

Configure `ufw` to deny all incoming traffic except SSH (from your IP only, on a non-standard port) and HTTPS (port 443, from Telegram's IP ranges). Enable `fail2ban` with `maxretry=3` and `bantime=3600`. Enforce SSH key-only authentication with `PasswordAuthentication no`. Run the bot process as a non-root user with systemd sandboxing (`NoNewPrivileges=true`, `ProtectSystem=strict`, `PrivateTmp=true`). Enable automatic security updates via `unattended-upgrades`.

---

## Core functionality patterns for a trading interface

### Viewing scans and market data

Push scan results using aiogram's `BufferedInputFile` for chart images and HTML-formatted code blocks for tabular data. Always use `matplotlib.use('Agg')` on the server (no display backend), generate charts into `io.BytesIO`, and **always call `plt.close(fig)` to prevent memory leaks** in the long-running bot process. For candlestick charts, `mplfinance` produces publication-quality output with `mpf.plot(df, type='candle', style='yahoo', volume=True)`. Use `figsize=(10, 6)` with `dpi=150` — wide aspect ratios render well on mobile.

For tabular scan results, HTML `<pre>` blocks with monospace formatting work well within the **4096-character message limit**. For larger outputs, implement paginated inline keyboards using aiogram's `CallbackData` factory to encode page numbers, with Previous/Next navigation buttons. The `aiogram-widgets` library provides ready-made `KeyboardPaginator` components. When results exceed reasonable pagination, send them as document attachments (up to 50 MB).

### Executing trades with confirmation flows

The trade execution pattern uses aiogram's FSM (Finite State Machine) with `StatesGroup` to manage multi-step flows: symbol selection → amount entry → order preview → confirmation → execution → result notification. Each state transition is explicit, and the FSM context (backed by Redis for persistence across restarts) stores intermediate data like the selected pair and amount.

```python
class OrderFlow(StatesGroup):
    select_pair = State()
    enter_amount = State()
    confirm_order = State()

@router.message(Command("buy"))
async def cmd_buy(message: Message, state: FSMContext):
    await state.set_state(OrderFlow.select_pair)
    await message.answer("Select pair:", reply_markup=pairs_keyboard())
```

The confirmation step uses time-limited HMAC tokens embedded in inline keyboard callback data. After the user confirms, the handler calls the BFF API, reports the result (fill price, order ID), and clears the FSM state. A `/cancel` command is available at every state to abort the flow. Portfolio commands (`/positions`, `/pnl`, `/balance`) format data in HTML tables with emoji indicators (🟢/🔴 for positive/negative PnL).

### System monitoring and troubleshooting

Commands like `/health`, `/logs`, `/errors`, and `/resources` call the BFF API, which uses `psutil` to gather CPU, memory, and disk metrics. Log viewing commands accept optional parameters (`/logs trading 20`) with hard caps on line counts. Error details can be fetched by ID and displayed with truncated tracebacks in `<pre>` blocks. For log streaming, implement a rate-limited buffer that batches log lines before sending, respecting Telegram's 1 message/second per-chat limit.

### AI-assisted debugging and CI/CD triggers

The Claude or OpenAI API can be invoked from within the bot for error analysis. The pattern: `/fix_error <error_id>` → bot fetches error context from BFF → sends to LLM API → displays suggested fix with Apply/Reject buttons → if approved, creates a git branch with the change. Projects like `claude-code-telegram` and `chatgpt-telegram-bot` demonstrate this integration. **Critical safety rule: never auto-apply AI-suggested changes to production trading logic without human review.** Restrict AI fixes to non-critical code paths, always route through staging, and maintain an audit log of all AI-suggested changes.

CI/CD triggers (`/deploy staging`, `/rollback`) should call the BFF API, which triggers pipelines via GitHub Actions API or Jenkins REST API. Production deployments require double confirmation with inline keyboards. Git operations (`/git_status`, `/git_pull`) should be read-only by default, with write operations restricted to admin role.

---

## Architecture patterns for reliability and responsiveness

### Message queues for async notifications

Use **Redis pub/sub** as the notification backbone. Trading engines, scanners, and monitoring services publish events to Redis channels (`trade_fills`, `alerts`, `system_events`). A background asyncio task in the bot subscribes to these channels and pushes formatted messages to Telegram:

```python
@dp.startup()
async def on_startup(bot: Bot):
    asyncio.create_task(notification_listener(bot, config.ADMIN_CHAT_ID))
```

For long-running operations (complex scans, batch orders), use **Celery** or **arq** (async-native task queue) to process work in background workers, publishing completion events back to Redis for the bot to pick up. This keeps the webhook handler fast and non-blocking.

### Priority-based notification management

Not all notifications deserve equal urgency. Implement a priority system: **critical** (margin calls, system down — send immediately), **high** (trade fills, price alerts — send immediately), **medium** (scan results — batch every 5 minutes), **low** (informational updates — batch every 30 minutes). This prevents notification spam while ensuring critical alerts are never delayed.

### Error handling and graceful degradation

Wrap BFF API calls with **circuit breakers** (using `aiobreaker` or `pybreaker`) that open after 5 consecutive failures and reset after 60 seconds. When the circuit is open, the bot returns cached data or a friendly "service temporarily unavailable" message rather than timing out. aiogram v3's `@router.error()` decorator provides global error handling, and you can register handlers for specific exception types (e.g., `httpx.ConnectError` → "Trading platform unreachable"). Use `tenacity` for configurable retry logic with exponential backoff on transient failures.

---

## Lessons from production trading bots

**Freqtrade** (45.5k GitHub stars) provides the gold standard reference. Its Telegram module uses an `@authorized_only` decorator as a single security gate, an RPC layer abstracting Telegram from trading logic, structured `RPCMessageType` enums for notifications, per-event verbosity control, and explicit 4096-character limit handling. Study `freqtrade/rpc/telegram.py` for battle-tested patterns.

**Hummingbot's Condor** (released December 2025 in v2.11) implements the exact architecture described in this report: a FastAPI API server on port 8000 with a separate Telegram bot (Condor) as a thin UI client. This validates the BFF + Telegram bot pattern for production trading systems, with real-time dashboards, interactive menus, and support for both centralized and decentralized exchanges.

Other notable references include **OctoBot** (AI-driven trading with web UI + Telegram + mobile), **EazeBot** (trade set management with stop-loss notifications), and the **Intelligent Trading Bot** (ML-based signal generation pushed to Telegram channels). For project templates, `bralbral/fastapi_aiogram_template` and `nessshon/aiogram-starlette-template` provide Docker-ready starting points with Redis, Nginx, and Certbot pre-configured.

Key production lessons from these communities: one bot token supports only one polling instance (running two causes conflicts), exchange API keys should never have withdrawal permissions, and systemd with `Restart=always` is the standard deployment pattern for VPS-hosted bots.

---

## Operational considerations that prevent outages

**Telegram API rate limits** constrain you to **1 message/second per individual chat**, **20 messages/minute per group**, and **30 messages/second globally** across all chats. The `limited_aiogram` package patches aiogram's Bot class to enforce these limits automatically with queuing. On 429 errors, parse the `retry_after` field and wait. Use separate message queues for individual chats versus groups since they have different limits.

**Monitor the bot itself** with systemd (`Restart=always`, `RestartSec=10`) for automatic restart on crashes, plus external uptime monitoring via UptimeRobot or self-hosted Uptime Kuma hitting your webhook health endpoint. The bot should send periodic heartbeat messages to a monitoring channel. Run `telemonitor` or a custom health check process that verifies the bot is responsive.

For **charts on mobile**, use matplotlib with `Agg` backend, `figsize=(10, 6)`, `dpi=150`, large fonts (14pt+), and `bbox_inches='tight'`. Always `buffer.seek(0)` before sending and `plt.close(fig)` after — both are common bug sources. `mplfinance` with the Yahoo style produces clean candlestick charts. For interactive charting, Plotly exports static PNGs via the `kaleido` engine.

---

## Conclusion

The Telegram + FastAPI BFF architecture works well for controlling a live trading platform, but only if security is treated as a first-class architectural concern rather than an afterthought. Three design principles should guide implementation. First, the bot must remain a **pure presentation layer** — every handler should follow the pattern of parse input, call BFF API, format response. The moment business logic creeps into bot handlers, you've created a maintenance and security liability. Second, **every destructive action needs friction** — time-limited HMAC tokens, single-use confirmation buttons, role-based authorization, and trade size limits enforced at multiple layers. Third, the **kill switch must work independently** — a separate monitoring process with its own exchange API credentials (cancel-only) that can halt trading via Redis even when the main bot is unresponsive.

The recommended technology stack is **aiogram v3** for the bot framework, **Redis** for FSM state storage, pub/sub notifications, rate limiting, and kill switch flags, **httpx** for async BFF API calls, **aiobreaker** for circuit breaking, and **structlog** for audit logging. Start with the `bralbral/fastapi_aiogram_template` boilerplate and study Freqtrade's `telegram.py` for production-hardened patterns. The newest validation of this architecture is Hummingbot's Condor (December 2025), which implements exactly this FastAPI API + Telegram bot pattern for live trading at scale.