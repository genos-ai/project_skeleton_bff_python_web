#!/usr/bin/env python3
"""
Example Entry Script.

Example entry point demonstrating CLI patterns, logging, and configuration.
All functionality is accessible through command-line options.

Usage:
    python cli.py --help
    python cli.py --action server --verbose
    python cli.py --action health --debug
    python cli.py --action config
    python cli.py --action test --test-type unit
"""

import os
import subprocess
import sys
from pathlib import Path

import click

# Ensure project root is in path for absolute imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.core.logging import get_logger, setup_logging


def validate_project_root() -> Path:
    """Validate that we're running from the project root."""
    if not (PROJECT_ROOT / ".project_root").exists():
        click.echo(
            click.style("Error: .project_root not found. Run from project root.", fg="red"),
            err=True,
        )
        sys.exit(1)
    return PROJECT_ROOT


@click.command()
@click.option(
    "--action",
    type=click.Choice(["server", "stop", "worker", "scheduler", "health", "config", "test", "info", "migrate", "telegram-poll"]),
    default="info",
    help="Action to perform.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output (INFO level logging).",
)
@click.option(
    "--debug", "-d",
    is_flag=True,
    help="Enable debug output (DEBUG level logging).",
)
@click.option(
    "--host",
    default=None,
    help="Server host (for server action).",
)
@click.option(
    "--port",
    default=None,
    type=int,
    help="Server port (for server action).",
)
@click.option(
    "--reload",
    is_flag=True,
    help="Enable auto-reload (for server action).",
)
@click.option(
    "--test-type",
    type=click.Choice(["all", "unit", "integration", "e2e"]),
    default="all",
    help="Test type to run (for test action).",
)
@click.option(
    "--coverage",
    is_flag=True,
    help="Run tests with coverage (for test action).",
)
@click.option(
    "--migrate-action",
    type=click.Choice(["upgrade", "downgrade", "current", "history", "autogenerate"]),
    default="current",
    help="Migration action (for migrate action).",
)
@click.option(
    "--revision",
    default="head",
    help="Target revision for upgrade/downgrade (default: head).",
)
@click.option(
    "-m", "--message",
    default=None,
    help="Migration message (for autogenerate action).",
)
@click.option(
    "--workers",
    default=1,
    type=int,
    help="Number of worker processes (for worker action).",
)
def main(
    action: str,
    verbose: bool,
    debug: bool,
    host: str | None,
    port: int | None,
    reload: bool,
    test_type: str,
    coverage: bool,
    migrate_action: str,
    revision: str,
    message: str | None,
    workers: int,
) -> None:
    """
    BFF Application Entry Point.

    Run the application server, background worker, task scheduler,
    check health, view configuration, or run tests.

    Examples:

        # Start development server
        python cli.py --action server --reload --verbose

        # Start background task worker
        python cli.py --action worker --verbose

        # Start task scheduler (for cron-based tasks)
        python cli.py --action scheduler --verbose

        # Check application health
        python cli.py --action health --debug

        # View loaded configuration
        python cli.py --action config

        # Run unit tests with coverage
        python cli.py --action test --test-type unit --coverage

        # Show application info
        python cli.py --action info

        # Database migrations
        python cli.py --action migrate --migrate-action current
        python cli.py --action migrate --migrate-action upgrade
        python cli.py --action migrate --migrate-action autogenerate -m "add users table"

        # Telegram bot (polling mode for local development)
        python cli.py --action telegram-poll --verbose

        # Stop a running server
        python cli.py --action stop
        python cli.py --action stop --port 8099
    """
    # Validate project root
    validate_project_root()

    # Configure logging based on verbosity
    if debug:
        log_level = "DEBUG"
    elif verbose:
        log_level = "INFO"
    else:
        log_level = "WARNING"

    setup_logging(level=log_level, format_type="console")

    import structlog.contextvars
    structlog.contextvars.bind_contextvars(frontend="cli")

    logger = get_logger(__name__)

    logger.debug("Starting application", extra={"action": action, "log_level": log_level})

    # Dispatch to action handlers
    if action == "server":
        run_server(logger, host, port, reload)
    elif action == "stop":
        stop_server(logger, port)
    elif action == "worker":
        run_worker(logger, workers)
    elif action == "scheduler":
        run_scheduler(logger)
    elif action == "health":
        check_health(logger)
    elif action == "config":
        show_config(logger)
    elif action == "test":
        run_tests(logger, test_type, coverage)
    elif action == "info":
        show_info(logger)
    elif action == "migrate":
        run_migrations(logger, migrate_action, revision, message)
    elif action == "telegram-poll":
        run_telegram_poll(logger)


def run_server(logger, host: str | None, port: int | None, reload: bool) -> None:
    """Start the FastAPI development server."""
    from modules.backend.core.config import get_app_config

    try:
        server_config = get_app_config().application["server"]
    except Exception as e:
        logger.error("Failed to load configuration.", extra={"error": str(e)})
        click.echo(
            click.style("Error: Could not load config/settings/application.yaml.", fg="red"),
            err=True,
        )
        sys.exit(1)

    server_host = host or server_config["host"]
    server_port = port or server_config["port"]

    logger.info(
        "Starting server",
        extra={"host": server_host, "port": server_port, "reload": reload},
    )

    cmd = [
        sys.executable, "-m", "uvicorn",
        "modules.backend.main:app",
        "--host", server_host,
        "--port", str(server_port),
    ]

    if reload:
        cmd.append("--reload")

    click.echo(f"Starting server at http://{server_host}:{server_port}")
    click.echo("Press Ctrl+C to stop\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Server stopped")
    except subprocess.CalledProcessError as e:
        logger.error("Server failed to start", extra={"exit_code": e.returncode})
        sys.exit(e.returncode)


def stop_server(logger, port: int | None) -> None:
    """Stop a running server by finding its process on the configured port."""
    import signal

    from modules.backend.core.config import get_app_config

    try:
        server_config = get_app_config().application["server"]
    except Exception as e:
        logger.error("Failed to load configuration.", extra={"error": str(e)})
        click.echo(click.style("Error: Could not load configuration.", fg="red"), err=True)
        sys.exit(1)

    server_port = port or server_config["port"]

    try:
        import subprocess as sp

        result = sp.run(
            ["lsof", "-ti", f":{server_port}"],
            capture_output=True, text=True,
        )
        pids = result.stdout.strip().split("\n")
        pids = [p.strip() for p in pids if p.strip()]

        if not pids:
            click.echo(f"No server running on port {server_port}.")
            return

        for pid in pids:
            os.kill(int(pid), signal.SIGINT)
            logger.info("Sent SIGINT to process", extra={"pid": pid, "port": server_port})

        click.echo(f"Server on port {server_port} stopped (PID: {', '.join(pids)}).")

    except Exception as e:
        logger.error("Failed to stop server", extra={"error": str(e)})
        click.echo(click.style(f"Error stopping server: {e}", fg="red"), err=True)
        sys.exit(1)


def run_worker(logger, workers: int) -> None:
    """Start the Taskiq background task worker."""
    logger.info("Starting background task worker", extra={"workers": workers})

    try:
        from modules.backend.core.config import get_redis_url
        redis_url = get_redis_url()
        logger.debug("Redis configured", extra={"redis_url": redis_url.split("@")[-1]})
    except Exception as e:
        logger.error("Failed to load Redis configuration.", extra={"error": str(e)})
        click.echo(
            click.style(f"Error: Redis not configured: {e}", fg="red"),
            err=True,
        )
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "taskiq",
        "worker",
        "modules.backend.tasks.broker:broker",
        "--workers", str(workers),
    ]

    click.echo(f"Starting Taskiq worker with {workers} worker(s)")
    click.echo("Press Ctrl+C to stop\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Worker stopped")
    except subprocess.CalledProcessError as e:
        logger.error("Worker failed to start", extra={"exit_code": e.returncode})
        sys.exit(e.returncode)


def run_scheduler(logger) -> None:
    """Start the Taskiq task scheduler for cron-based tasks."""
    logger.info("Starting task scheduler")

    try:
        from modules.backend.core.config import get_redis_url
        redis_url = get_redis_url()
        logger.debug("Redis configured", extra={"redis_url": redis_url.split("@")[-1]})
    except Exception as e:
        logger.error("Failed to load Redis configuration.", extra={"error": str(e)})
        click.echo(
            click.style(f"Error: Redis not configured: {e}", fg="red"),
            err=True,
        )
        sys.exit(1)

    # Register scheduled tasks before starting scheduler
    try:
        from modules.backend.tasks.scheduled import register_scheduled_tasks, SCHEDULED_TASKS
        register_scheduled_tasks()

        click.echo("Registered scheduled tasks:")
        for task_name, config in SCHEDULED_TASKS.items():
            schedule = config["schedule"][0].get("cron", "N/A")
            click.echo(f"  - {task_name}: {schedule}")
        click.echo()
    except Exception as e:
        logger.error("Failed to register scheduled tasks", extra={"error": str(e)})
        click.echo(
            click.style(f"Error registering tasks: {e}", fg="red"),
            err=True,
        )
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "taskiq",
        "scheduler",
        "modules.backend.tasks.scheduler:scheduler",
    ]

    click.echo("Starting Taskiq scheduler")
    click.echo("WARNING: Run only ONE scheduler instance to avoid duplicate task execution")
    click.echo("Press Ctrl+C to stop\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")
    except subprocess.CalledProcessError as e:
        logger.error("Scheduler failed to start", extra={"exit_code": e.returncode})
        sys.exit(e.returncode)


def run_telegram_poll(logger) -> None:
    """Start the Telegram bot in polling mode for local development."""
    import asyncio

    from modules.backend.core.config import get_app_config

    features = get_app_config().features
    if not features.get("channel_telegram_enabled"):
        click.echo(
            click.style(
                "Error: channel_telegram_enabled is false in features.yaml. "
                "Enable it to use the Telegram bot.",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    logger.info("Starting Telegram bot in polling mode")

    try:
        from modules.telegram.bot import create_bot, create_dispatcher

        bot = create_bot()
        dp = create_dispatcher()

        click.echo("Starting Telegram bot (polling mode)")
        click.echo("Send /start to your bot on Telegram")
        click.echo("Press Ctrl+C to stop\n")

        asyncio.run(_run_polling(bot, dp, logger))

    except RuntimeError as e:
        logger.error("Telegram bot failed to start", extra={"error": str(e)})
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


async def _run_polling(bot, dp, logger) -> None:
    """Run the bot polling loop."""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted, starting polling")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Telegram bot stopped")
    finally:
        await bot.session.close()


def check_health(logger) -> None:
    """Check application health by testing imports and configuration."""
    click.echo("Checking application health...\n")

    checks = []

    # Check 1: Core imports
    try:
        from modules.backend.core.config import get_settings, get_app_config
        from modules.backend.core.logging import get_logger
        from modules.backend.core.exceptions import ApplicationError
        checks.append(("Core imports", True, None))
        logger.debug("Core imports successful")
    except Exception as e:
        checks.append(("Core imports", False, str(e)))
        logger.error("Core imports failed", extra={"error": str(e)})

    # Check 2: Configuration loading
    try:
        app_config = get_app_config()
        app_name = app_config.application.get("name")
        checks.append(("YAML configuration", True, f"App: {app_name}"))
        logger.debug("Configuration loaded", extra={"app_name": app_name})
    except Exception as e:
        checks.append(("YAML configuration", False, str(e)))
        logger.error("Configuration failed", extra={"error": str(e)})

    # Check 3: Environment settings
    try:
        app_env = get_app_config().application["environment"]
        checks.append(("Environment settings", True, f"Env: {app_env}"))
        logger.debug("Settings loaded", extra={"env": app_env})
    except Exception as e:
        checks.append(("Environment settings", False, str(e)))
        logger.warning("Environment settings not configured (expected for skeleton)")

    # Check 4: FastAPI app
    try:
        from modules.backend.main import get_app
        app = get_app()
        checks.append(("FastAPI application", True, f"Title: {app.title}"))
        logger.debug("FastAPI app loaded", extra={"title": app.title})
    except Exception as e:
        checks.append(("FastAPI application", False, str(e)))
        logger.error("FastAPI app failed", extra={"error": str(e)})

    # Check 5: Database models
    try:
        from modules.backend.models.base import Base, TimestampMixin, UUIDMixin
        checks.append(("Database models", True, None))
        logger.debug("Database models loaded")
    except Exception as e:
        checks.append(("Database models", False, str(e)))
        logger.error("Database models failed", extra={"error": str(e)})

    # Check 6: Schemas
    try:
        from modules.backend.schemas.base import ApiResponse, ErrorResponse
        checks.append(("API schemas", True, None))
        logger.debug("Schemas loaded")
    except Exception as e:
        checks.append(("API schemas", False, str(e)))
        logger.error("Schemas failed", extra={"error": str(e)})

    # Display results
    click.echo("Health Check Results:")
    click.echo("-" * 50)

    all_passed = True
    for name, passed, detail in checks:
        status = click.style("✓ PASS", fg="green") if passed else click.style("✗ FAIL", fg="red")
        detail_str = f" ({detail})" if detail else ""
        click.echo(f"  {status}  {name}{detail_str}")
        if not passed:
            all_passed = False

    click.echo("-" * 50)

    if all_passed:
        click.echo(click.style("\nAll checks passed!", fg="green"))
    else:
        click.echo(click.style("\nSome checks failed. See details above.", fg="yellow"))
        click.echo("Note: Environment settings require config/.env to be configured.")


def show_config(logger) -> None:
    """Display loaded configuration."""
    click.echo("Application Configuration:\n")

    try:
        from modules.backend.core.config import get_app_config

        app_config = get_app_config()

        click.echo("Application Settings (from YAML):")
        click.echo("-" * 40)
        for key, value in app_config.application.items():
            click.echo(f"  {key}: {value}")

        click.echo("\nDatabase Settings (from YAML):")
        click.echo("-" * 40)
        for key, value in app_config.database.items():
            click.echo(f"  {key}: {value}")

        click.echo("\nLogging Settings (from YAML):")
        click.echo("-" * 40)
        for key, value in app_config.logging.items():
            if isinstance(value, dict):
                click.echo(f"  {key}:")
                for k, v in value.items():
                    click.echo(f"    {k}: {v}")
            else:
                click.echo(f"  {key}: {value}")

        click.echo("\nFeature Flags (from YAML):")
        click.echo("-" * 40)
        for key, value in app_config.features.items():
            click.echo(f"  {key}: {value}")

        logger.info("Configuration displayed successfully")

    except Exception as e:
        logger.error("Failed to load configuration", extra={"error": str(e)})
        click.echo(click.style(f"Error loading configuration: {e}", fg="red"))
        sys.exit(1)


def run_tests(logger, test_type: str, coverage: bool) -> None:
    """Run the test suite."""
    logger.info("Running tests", extra={"type": test_type, "coverage": coverage})

    cmd = [sys.executable, "-m", "pytest"]

    # Select test directory based on type
    if test_type == "unit":
        cmd.append("tests/unit")
    elif test_type == "integration":
        cmd.append("tests/integration")
    elif test_type == "e2e":
        cmd.append("tests/e2e")
    else:
        cmd.append("tests/")

    # Add verbosity
    cmd.append("-v")

    # Add coverage if requested
    if coverage:
        cmd.extend(["--cov=modules/backend", "--cov-report=term-missing"])

    click.echo(f"Running: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except FileNotFoundError:
        logger.error("pytest not found. Install with: pip install pytest")
        sys.exit(1)


def run_migrations(
    logger,
    migrate_action: str,
    revision: str,
    message: str | None,
) -> None:
    """Run database migrations using Alembic."""
    logger.info(
        "Running migrations",
        extra={"action": migrate_action, "revision": revision},
    )

    # Alembic config path
    alembic_ini = PROJECT_ROOT / "modules" / "backend" / "migrations" / "alembic.ini"

    if not alembic_ini.exists():
        click.echo(
            click.style("Error: modules/backend/migrations/alembic.ini not found.", fg="red"),
            err=True,
        )
        sys.exit(1)

    # Build alembic command
    cmd = [sys.executable, "-m", "alembic", "-c", str(alembic_ini)]

    if migrate_action == "upgrade":
        cmd.extend(["upgrade", revision])
        click.echo(f"Upgrading database to revision: {revision}")
    elif migrate_action == "downgrade":
        cmd.extend(["downgrade", revision])
        click.echo(f"Downgrading database to revision: {revision}")
    elif migrate_action == "current":
        cmd.append("current")
        click.echo("Showing current database revision...")
    elif migrate_action == "history":
        cmd.extend(["history", "--verbose"])
        click.echo("Showing migration history...")
    elif migrate_action == "autogenerate":
        if not message:
            click.echo(
                click.style("Error: --message/-m required for autogenerate.", fg="red"),
                err=True,
            )
            sys.exit(1)
        cmd.extend(["revision", "--autogenerate", "-m", message])
        click.echo(f"Generating migration: {message}")

    click.echo()

    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            logger.error("Migration failed", extra={"exit_code": result.returncode})
            sys.exit(result.returncode)
        logger.info("Migration completed successfully")
    except FileNotFoundError:
        logger.error("alembic not found. Install with: pip install alembic")
        sys.exit(1)


def show_info(logger) -> None:
    """Display application information."""
    click.echo("BFF Python Web Application")
    click.echo("=" * 40)

    try:
        from modules.backend.core.config import get_app_config
        app_config = get_app_config()
        click.echo(f"Name: {app_config.application.get('name')}")
        click.echo(f"Version: {app_config.application.get('version')}")
        click.echo(f"Description: {app_config.application.get('description')}")
    except Exception as e:
        logger.error(
            "Failed to load application configuration",
            extra={"error": str(e)},
        )
        click.echo(
            click.style(
                "Error: Could not load application.yaml configuration.",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    click.echo()
    click.echo("Available Actions:")
    click.echo("  --action server    Start the development server")
    click.echo("  --action worker    Start background task worker")
    click.echo("  --action scheduler Start task scheduler (cron-based tasks)")
    click.echo("  --action health    Check application health")
    click.echo("  --action config    Display configuration")
    click.echo("  --action test      Run test suite")
    click.echo("  --action stop           Stop a running server")
    click.echo("  --action migrate        Run database migrations")
    click.echo("  --action telegram-poll  Start Telegram bot (polling, local dev)")
    click.echo("  --action info           Show this information")
    click.echo()
    click.echo("Logging Options:")
    click.echo("  --verbose, -v     Enable INFO level logging")
    click.echo("  --debug, -d       Enable DEBUG level logging")
    click.echo()
    click.echo("Examples:")
    click.echo("  python cli.py --action server --reload --verbose")
    click.echo("  python cli.py --action worker --workers 2 --verbose")
    click.echo("  python cli.py --action scheduler --verbose")
    click.echo("  python cli.py --action health --debug")
    click.echo("  python cli.py --action test --test-type unit --coverage")
    click.echo("  python cli.py --action migrate --migrate-action current")
    click.echo("  python cli.py --action migrate --migrate-action upgrade")
    click.echo("  python cli.py --action migrate --migrate-action autogenerate -m 'add users'")
    click.echo("  python cli.py --action telegram-poll --verbose")

    logger.debug("Info displayed")


if __name__ == "__main__":
    main()
