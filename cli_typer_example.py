#!/usr/bin/env python3
"""
CLI Client.

Interactive command-line client for the backend API.
Built with Typer for type-safe commands and Rich for formatted output.

Usage:
    python cli_typer_example.py --help                    # Show help

    # Server management
    python cli_typer_example.py server start              # Start FastAPI server
    python cli_typer_example.py server start --reload     # Start with auto-reload
    python cli_typer_example.py server worker             # Start background worker
    python cli_typer_example.py server scheduler          # Start task scheduler

    # Database migrations
    python cli_typer_example.py db current                # Show current revision
    python cli_typer_example.py db upgrade                # Upgrade to latest
    python cli_typer_example.py db generate -m "message"  # Generate migration

    # Testing
    python cli_typer_example.py test run                  # Run all tests
    python cli_typer_example.py test unit --coverage      # Unit tests with coverage

    # Health checks
    python cli_typer_example.py health check              # Local health check (no server)
    python cli_typer_example.py health status             # Backend health (requires server)
    python cli_typer_example.py health ping               # Ping backend

    # System info
    python cli_typer_example.py system info               # Show app info
    python cli_typer_example.py system config             # Show configuration
    python cli_typer_example.py system env                # Show environment

    # Interactive mode
    python cli_typer_example.py shell                     # Start interactive shell

Options:
    --verbose, -v     Enable verbose output
    --debug           Enable debug mode (detailed logging)
    --help            Show help message
"""

import asyncio
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console

# Add project root to path for absolute imports
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def _validate_project_root() -> None:
    """Validate that we're running from the project root."""
    if not (project_root / ".project_root").exists():
        console.print("[red]Error: .project_root not found. Run from project root.[/red]")
        raise typer.Exit(1)


from modules.cli.commands import db_app, health_app, server_app, system_app, test_app

# Create main app
app = typer.Typer(
    name="cli",
    help="BFF Application CLI - Server management, database, testing, and more.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# Register command groups
app.add_typer(server_app, name="server")
app.add_typer(db_app, name="db")
app.add_typer(test_app, name="test")
app.add_typer(health_app, name="health")
app.add_typer(system_app, name="system")


@app.command()
def shell() -> None:
    """
    Start interactive shell mode.

    Provides a REPL-style interface for running commands interactively.
    """
    from modules.cli.shell import run_shell

    asyncio.run(run_shell())


@app.callback()
def main(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output (INFO level logging)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode (DEBUG level logging)",
    ),
) -> None:
    """
    BFF Application CLI.

    Server management, database migrations, testing, health checks, and more.
    Built with Typer for type-safe commands and Rich for formatted output.
    """
    # Validate project root
    _validate_project_root()

    # Configure logging based on flags
    if debug:
        from modules.backend.core.logging import setup_logging
        setup_logging(level="DEBUG", format_type="console")
        console.print("[dim]Debug mode enabled[/dim]")
    elif verbose:
        from modules.backend.core.logging import setup_logging
        setup_logging(level="INFO", format_type="console")


if __name__ == "__main__":
    app()
