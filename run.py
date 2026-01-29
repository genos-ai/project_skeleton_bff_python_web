#!/usr/bin/env python3
"""
Application Entry Script.

Main entry point for the BFF application. All functionality is accessible
through command-line options.

Usage:
    python run.py --help
    python run.py --action server --verbose
    python run.py --action health --debug
    python run.py --action config
    python run.py --action test --test-type unit
"""

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
    type=click.Choice(["server", "health", "config", "test", "info"]),
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
def main(
    action: str,
    verbose: bool,
    debug: bool,
    host: str | None,
    port: int | None,
    reload: bool,
    test_type: str,
    coverage: bool,
) -> None:
    """
    BFF Application Entry Point.

    Run the application server, check health, view configuration,
    or run tests.

    Examples:

        # Start development server
        python run.py --action server --reload --verbose

        # Check application health
        python run.py --action health --debug

        # View loaded configuration
        python run.py --action config

        # Run unit tests with coverage
        python run.py --action test --test-type unit --coverage

        # Show application info
        python run.py --action info
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
    logger = get_logger(__name__)

    logger.debug("Starting application", extra={"action": action, "log_level": log_level})

    # Dispatch to action handlers
    if action == "server":
        run_server(logger, host, port, reload)
    elif action == "health":
        check_health(logger)
    elif action == "config":
        show_config(logger)
    elif action == "test":
        run_tests(logger, test_type, coverage)
    elif action == "info":
        show_info(logger)


def run_server(logger, host: str | None, port: int | None, reload: bool) -> None:
    """Start the FastAPI development server."""
    from modules.backend.core.config import get_settings

    try:
        settings = get_settings()
        server_host = host or settings.server_host
        server_port = port or settings.server_port
    except Exception as e:
        logger.warning(
            "Could not load settings, using defaults",
            extra={"error": str(e)},
        )
        server_host = host or "127.0.0.1"
        server_port = port or 8000

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
        app_name = app_config.application.get("name", "Unknown")
        checks.append(("YAML configuration", True, f"App: {app_name}"))
        logger.debug("Configuration loaded", extra={"app_name": app_name})
    except Exception as e:
        checks.append(("YAML configuration", False, str(e)))
        logger.error("Configuration failed", extra={"error": str(e)})

    # Check 3: Environment settings
    try:
        settings = get_settings()
        checks.append(("Environment settings", True, f"Env: {settings.app_env}"))
        logger.debug("Settings loaded", extra={"env": settings.app_env})
    except Exception as e:
        checks.append(("Environment settings", False, str(e)))
        logger.warning("Environment settings not configured (expected for skeleton)")

    # Check 4: FastAPI app
    try:
        from modules.backend.main import app
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


def show_info(logger) -> None:
    """Display application information."""
    click.echo("BFF Python Web Application")
    click.echo("=" * 40)

    try:
        from modules.backend.core.config import get_app_config
        app_config = get_app_config()
        click.echo(f"Name: {app_config.application.get('name', 'Unknown')}")
        click.echo(f"Version: {app_config.application.get('version', 'Unknown')}")
        click.echo(f"Description: {app_config.application.get('description', 'N/A')}")
    except Exception:
        click.echo("Name: BFF Application")
        click.echo("Version: 0.1.0")

    click.echo()
    click.echo("Available Actions:")
    click.echo("  --action server   Start the development server")
    click.echo("  --action health   Check application health")
    click.echo("  --action config   Display configuration")
    click.echo("  --action test     Run test suite")
    click.echo("  --action info     Show this information")
    click.echo()
    click.echo("Logging Options:")
    click.echo("  --verbose, -v     Enable INFO level logging")
    click.echo("  --debug, -d       Enable DEBUG level logging")
    click.echo()
    click.echo("Examples:")
    click.echo("  python run.py --action server --reload --verbose")
    click.echo("  python run.py --action health --debug")
    click.echo("  python run.py --action test --test-type unit --coverage")

    logger.debug("Info displayed")


if __name__ == "__main__":
    main()
