# Telegram Bot Integration Guide

> Reference documentation for integrating Telegram bots using aiogram v3 with FastAPI.

**Version:** 1.0.0
**Last Updated:** 2026-02-11

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Module Structure](#module-structure)
4. [Configuration](#configuration)
5. [Core Components](#core-components)
6. [Handlers](#handlers)
7. [Middlewares](#middlewares)
8. [FSM (Finite State Machine)](#fsm-finite-state-machine)
9. [Keyboards](#keyboards)
10. [Callback Data](#callback-data)
11. [Backend Integration](#backend-integration)
12. [Security](#security)
13. [Deployment](#deployment)
14. [Best Practices](#best-practices)

---

## Overview

### Why aiogram v3?

| Feature | aiogram v3 | python-telegram-bot |
|---------|-----------|---------------------|
| Async-first | ✅ Native asyncio | ✅ Added in v20 |
| Type hints | ✅ Full Pydantic v2 | ⚠️ Partial |
| FSM | ✅ Built-in with Redis | ⚠️ ConversationHandler |
| Middleware | ✅ Powerful system | ❌ Limited |
| FastAPI integration | ✅ Excellent | ⚠️ Requires workarounds |

### Key Benefits

- **Shared Event Loop**: Bot runs on the same Uvicorn process as FastAPI
- **Webhook Mode**: Production-ready with secret token validation
- **Type Safety**: Full type hints with Pydantic v2 models
- **Middleware System**: Auth, rate limiting, logging out of the box
- **FSM Support**: Multi-step conversations with Redis persistence

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
├─────────────────────────────────────────────────────────────┤
│  /api/*          │  /webhook/telegram  │  /health/*         │
│  REST Endpoints  │  Telegram Webhook   │  Health Checks     │
├─────────────────────────────────────────────────────────────┤
│                    Shared Uvicorn Process                    │
│                    (Single Event Loop)                       │
├─────────────────────────────────────────────────────────────┤
│  modules/backend/  │  modules/telegram/  │  modules/frontend/│
│  Business Logic    │  Bot Handlers       │  Web UI           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Telegram API   │
                    │  (Webhook POST) │
                    └─────────────────┘
```

### Design Principles

1. **Bot as Thin Presentation Layer**: All business logic lives in `modules/backend/`
2. **Service Calls**: Bot handlers call backend services, never direct DB access
3. **Shared Infrastructure**: Same Redis, same logging, same config system

---

## Module Structure

```
modules/telegram/
├── __init__.py          # Module exports, bot factory functions
├── bot.py               # Bot and Dispatcher creation
├── webhook.py           # FastAPI webhook router
├── handlers/            # Command and message handlers
│   ├── __init__.py      # Router aggregation
│   ├── common.py        # /start, /help, /cancel, /status
│   └── example.py       # Example patterns (FSM, callbacks)
├── middlewares/         # Request processing middlewares
│   ├── __init__.py      # Middleware setup
│   ├── auth.py          # User ID whitelisting
│   ├── logging.py       # Structured logging
│   └── rate_limit.py    # Rate limiting
├── keyboards/           # UI components
│   ├── __init__.py
│   └── common.py        # Keyboard builders
├── states/              # FSM state definitions
│   ├── __init__.py
│   └── example.py       # Example states
└── callbacks/           # Callback data factories
    ├── __init__.py
    └── common.py        # Common callbacks
```

---

## Configuration

### Environment Variables

Add to `config/.env`:

```bash
# =============================================================================
# Telegram Bot Configuration
# =============================================================================

# Bot token from @BotFather (required)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Webhook secret for validation (recommended for production)
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
TELEGRAM_WEBHOOK_SECRET=your-secret-token-here

# Webhook path (default: /webhook/telegram)
# TELEGRAM_WEBHOOK_PATH=/webhook/telegram

# Authorized user IDs (comma-separated)
# First user is admin, rest are traders
# Get your ID from @userinfobot
TELEGRAM_AUTHORIZED_USERS=123456789,987654321
```

### Settings Class

The settings are loaded in `modules/backend/core/config.py`:

```python
class Settings(BaseSettings):
    # ... other settings ...

    # Telegram Bot
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_webhook_path: str = "/webhook/telegram"
    telegram_authorized_users: list[int] = []
```

---

## Core Components

### Bot Initialization

```python
# modules/telegram/bot.py

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

def create_bot() -> Bot:
    """Create configured Bot instance."""
    settings = get_settings()
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

def create_dispatcher() -> Dispatcher:
    """Create Dispatcher with routers and middlewares."""
    dp = Dispatcher(storage=MemoryStorage())
    setup_middlewares(dp)
    for router in get_all_routers():
        dp.include_router(router)
    return dp
```

### FastAPI Integration

```python
# In your FastAPI app setup (e.g., main.py)

from fastapi import FastAPI
from contextlib import asynccontextmanager

from modules.telegram import create_bot, create_dispatcher
from modules.telegram.webhook import get_webhook_router
from modules.telegram.bot import setup_webhook, cleanup_bot

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize bot
    settings = get_settings()
    if settings.telegram_bot_token:
        bot = create_bot()
        dp = create_dispatcher()

        # Setup webhook (production)
        if settings.app_env == "production":
            webhook_url = f"https://yourdomain.com{settings.telegram_webhook_path}"
            await setup_webhook(bot, webhook_url, settings.telegram_webhook_secret)

        # Include webhook router
        app.include_router(get_webhook_router(bot, dp))

        yield

        # Shutdown: Cleanup
        await cleanup_bot(bot)
    else:
        yield

app = FastAPI(lifespan=lifespan)
```

---

## Handlers

### Handler Structure

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="my_feature")

@router.message(Command("mycommand"))
async def cmd_mycommand(message: Message, user_role: str) -> None:
    """Handle /mycommand."""
    await message.answer(f"Hello! Your role is {user_role}")
```

### Registering Handlers

Add new handlers to `modules/telegram/handlers/__init__.py`:

```python
from modules.telegram.handlers.my_feature import router as my_feature_router

def get_all_routers() -> list[Router]:
    return [
        common_router,
        example_router,
        my_feature_router,  # Add your router
    ]
```

---

## Middlewares

### Middleware Order

```python
# modules/telegram/middlewares/__init__.py

def setup_middlewares(dp: Dispatcher) -> None:
    # 1. Logging (outer) - Log all updates
    dp.update.outer_middleware(LoggingMiddleware())

    # 2. Auth (outer) - Check authorization
    dp.update.outer_middleware(AuthMiddleware())

    # 3. Rate limiting (inner) - After auth passes
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
```

### Custom Middleware

```python
from aiogram import BaseMiddleware
from typing import Any, Awaitable, Callable

class MyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Before handler
        data["my_data"] = "value"

        result = await handler(event, data)

        # After handler
        return result
```

---

## FSM (Finite State Machine)

### Defining States

```python
# modules/telegram/states/my_form.py

from aiogram.fsm.state import State, StatesGroup

class MyForm(StatesGroup):
    step_1 = State()
    step_2 = State()
    confirming = State()
```

### Using FSM in Handlers

```python
from aiogram.fsm.context import FSMContext
from modules.telegram.states.my_form import MyForm

@router.message(Command("start_form"))
async def start_form(message: Message, state: FSMContext) -> None:
    await state.set_state(MyForm.step_1)
    await message.answer("Enter value for step 1:")

@router.message(MyForm.step_1)
async def process_step_1(message: Message, state: FSMContext) -> None:
    await state.update_data(step_1_value=message.text)
    await state.set_state(MyForm.step_2)
    await message.answer("Enter value for step 2:")

@router.message(MyForm.step_2)
async def process_step_2(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await message.answer(f"Done! Step 1: {data['step_1_value']}, Step 2: {message.text}")
```

### Redis Storage (Production)

```python
from aiogram.fsm.storage.redis import RedisStorage

storage = RedisStorage.from_url(settings.redis_url)
dp = Dispatcher(storage=storage)
```

---

## Keyboards

### Reply Keyboards

```python
from aiogram.utils.keyboard import ReplyKeyboardBuilder

def get_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="Option 1")
    builder.button(text="Option 2")
    builder.adjust(2)  # 2 buttons per row
    return builder.as_markup(resize_keyboard=True)
```

### Inline Keyboards

```python
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_action_keyboard(item_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="View",
        callback_data=ItemCallback(action="view", item_id=item_id)
    )
    builder.button(
        text="Delete",
        callback_data=ItemCallback(action="delete", item_id=item_id)
    )
    return builder.as_markup()
```

---

## Callback Data

### Defining Callback Data

```python
from aiogram.filters.callback_data import CallbackData

class ItemCallback(CallbackData, prefix="item"):
    action: str      # view, edit, delete
    item_id: str
    page: int = 0    # Optional with default
```

### Handling Callbacks

```python
from aiogram import F

@router.callback_query(ItemCallback.filter(F.action == "view"))
async def handle_view(callback: CallbackQuery, callback_data: ItemCallback) -> None:
    item_id = callback_data.item_id
    await callback.message.edit_text(f"Viewing item {item_id}")
    await callback.answer()  # Remove loading state
```

---

## Backend Integration

### Calling Backend Services

```python
import httpx
from modules.backend.core.config import get_settings

async def call_backend_api(endpoint: str, method: str = "GET", **kwargs) -> dict:
    """Call the backend API from Telegram handlers."""
    settings = get_settings()
    base_url = f"http://localhost:{settings.server_port}"

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=f"{base_url}{endpoint}",
            headers={"X-Frontend-ID": "telegram"},
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

# Usage in handler
@router.message(Command("balance"))
async def cmd_balance(message: Message, telegram_user: User) -> None:
    try:
        data = await call_backend_api(f"/api/users/{telegram_user.id}/balance")
        await message.answer(f"Balance: {data['balance']}")
    except httpx.HTTPError as e:
        await message.answer("Failed to fetch balance. Please try again.")
```

### Direct Service Calls

For internal calls, you can import services directly:

```python
from modules.backend.services.user_service import UserService

@router.message(Command("profile"))
async def cmd_profile(message: Message, telegram_user: User) -> None:
    service = UserService()
    user = await service.get_by_telegram_id(telegram_user.id)
    if user:
        await message.answer(f"Profile: {user.name}")
```

---

## Security

### User ID Whitelisting

Telegram user IDs are immutable integers that cannot be spoofed within the Telegram API.

```python
# config/.env
TELEGRAM_AUTHORIZED_USERS=123456789,987654321

# First user (123456789) is admin
# Remaining users are traders
```

### Role-Based Access

```python
from modules.telegram.middlewares.auth import require_role

@router.message(Command("admin_only"))
@require_role("admin")
async def admin_handler(message: Message, user_role: str) -> None:
    await message.answer("Admin command executed")
```

### Webhook Secret Validation

```python
# Automatically validated in webhook.py
secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
if not hmac.compare_digest(secret_header, webhook_secret):
    return Response(status_code=403)
```

### Security Best Practices

1. **Never expose bot token** in logs or error messages
2. **Use webhook secret** in production
3. **Whitelist users** - don't allow public access
4. **Rate limit** to prevent abuse
5. **Log all access attempts** for audit trail
6. **Validate all input** before processing

---

## Deployment

### Development (Polling)

For local development without webhook:

```python
# scripts/run_telegram_polling.py

import asyncio
from modules.telegram import create_bot, create_dispatcher

async def main():
    bot = create_bot()
    dp = create_dispatcher()

    # Start polling (development only)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

### Production (Webhook)

1. **Set webhook URL** in environment:
   ```bash
   TELEGRAM_WEBHOOK_SECRET=your-secret-here
   ```

2. **Configure HTTPS** (required by Telegram):
   - Use a reverse proxy (nginx, Caddy)
   - Or cloud provider's load balancer

3. **Startup sequence**:
   ```python
   # In FastAPI lifespan
   await setup_webhook(bot, webhook_url, secret_token)
   ```

### Health Check

```bash
curl https://yourdomain.com/webhook/telegram/health
# {"status": "healthy", "webhook_path": "/webhook/telegram"}
```

---

## Best Practices

### 1. Handler Organization

```
handlers/
├── common.py       # Universal commands
├── admin.py        # Admin-only commands
├── trading.py      # Trading feature handlers
└── settings.py     # User settings handlers
```

### 2. Error Handling

```python
@router.message(Command("risky"))
async def risky_handler(message: Message) -> None:
    try:
        result = await some_risky_operation()
        await message.answer(f"Success: {result}")
    except SpecificError as e:
        logger.error("Operation failed", extra={"error": str(e)})
        await message.answer("Operation failed. Please try again.")
    except Exception as e:
        logger.exception("Unexpected error")
        await message.answer("An unexpected error occurred.")
```

### 3. Message Formatting

```python
# Use HTML parse mode (configured in bot.py)
await message.answer(
    "<b>Bold</b>, <i>italic</i>, <code>code</code>\n"
    "<a href='https://example.com'>Link</a>"
)
```

### 4. Long Operations

```python
from aiogram.types import ChatAction

@router.message(Command("slow"))
async def slow_handler(message: Message, bot: Bot) -> None:
    # Show typing indicator
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    result = await slow_operation()

    await message.answer(f"Done: {result}")
```

### 5. Testing

```python
# tests/unit/telegram/test_handlers.py

import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_start_command():
    message = AsyncMock()
    message.from_user = MagicMock(id=123, first_name="Test")

    await cmd_start(
        message=message,
        telegram_user=message.from_user,
        user_role="admin",
    )

    message.answer.assert_called_once()
    assert "Welcome" in message.answer.call_args[0][0]
```

---

## Proactive Notifications

The bot can send messages to users proactively (alerts, notifications) without waiting for user input.

### Notification Service

```python
from modules.telegram.services import send_alert, send_notification, AlertType

# Simple alert
await send_alert(
    user_id=123456789,
    message="Your task has completed!",
    alert_type=AlertType.SUCCESS,
)

# Rich notification with data
await send_notification(
    user_id=123456789,
    title="Export Ready",
    body="Your data export has completed",
    alert_type=AlertType.SUCCESS,
    data={"file_size": "2.5 MB", "records": "1,234"},
)
```

### Alert Types

| Type | Emoji | Use Case |
|------|-------|----------|
| `INFO` | ℹ️ | General information |
| `SUCCESS` | ✅ | Successful operations |
| `WARNING` | ⚠️ | Warnings, approaching limits |
| `ERROR` | ❌ | Errors, failures |
| `SYSTEM` | 🔧 | System notifications |

### Convenience Methods

```python
from modules.telegram.services import get_notification_service

service = get_notification_service()

# Success notification
await service.send_success(
    user_id=123456789,
    title="Task Completed",
    message="Your background job has finished",
    data={"duration": "5.2s"},
)

# Warning notification
await service.send_warning(
    user_id=123456789,
    title="Storage Warning",
    message="You are approaching your storage limit",
)

# Error notification
await service.send_error(
    user_id=123456789,
    title="Task Failed",
    error_message="Unable to process your request",
    context={"task_id": "123"},
)

# System notification
await service.send_system(
    user_id=123456789,
    title="Scheduled Maintenance",
    message="System will be down for maintenance at 2:00 AM UTC",
)
```

### Integration with Background Tasks

```python
# modules/backend/tasks/scheduled.py

async def check_pending_notifications():
    """Process pending notifications every minute."""
    from modules.telegram.services import get_notification_service

    service = get_notification_service()
    pending = await get_pending_notifications()

    for notification in pending:
        result = await service.send_alert(
            user_id=notification.user_telegram_id,
            title=notification.title,
            body=notification.body,
            alert_type=notification.alert_type,
        )
        if result.success:
            await mark_notification_sent(notification.id)
```

### Rate Limiting

The notification service includes built-in rate limiting:
- 20 messages per minute per user (configurable)
- Automatic tracking and enforcement
- Returns `rate_limited=True` when limit exceeded

```python
result = await send_alert(user_id=123, message="Alert!")

if result.rate_limited:
    # Handle rate limit (queue for later, skip, etc.)
    pass
```

### Broadcast to Multiple Users

```python
service = get_notification_service()

results = await service.broadcast(
    user_ids=[123, 456, 789],
    text="System maintenance in 1 hour",
    delay_between=0.05,  # 50ms between sends
)

success_count = sum(1 for r in results if r.success)
```

---

## Related Documentation

- [Background Tasks](20-background-tasks.md) - Taskiq integration
- [Observability](12-observability.md) - Logging and monitoring
- [Authentication](09-authentication.md) - Security patterns
- [Research Reference](../04-external-references/telegram_bot_control_interface.md) - Original research document

---

## Changelog

### 1.1.0 (2026-02-13)
- Added NotificationService for proactive alerts
- Added convenience methods (send_success, send_warning, send_error, send_system)
- Added rate limiting for outbound messages
- Added broadcast functionality
- Added integration examples with background tasks

### 1.0.0 (2026-02-11)
- Initial documentation
- aiogram v3 integration patterns
- Webhook and polling modes
- Middleware system (auth, logging, rate limiting)
- FSM patterns
- Keyboard builders
- Callback data factories
