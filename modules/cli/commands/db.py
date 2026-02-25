"""
Database Commands.

Commands for database migrations using Alembic.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Database migration commands")
console = Console()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = PROJECT_ROOT / "modules" / "backend" / "migrations" / "alembic.ini"


def _check_alembic() -> None:
    """Check that alembic.ini exists."""
    if not ALEMBIC_INI.exists():
        console.print("[red]Error: modules/backend/migrations/alembic.ini not found[/red]")
        raise typer.Exit(1)


def _run_alembic(args: list[str]) -> None:
    """Run an alembic command."""
    cmd = [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI)] + args

    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            raise typer.Exit(result.returncode)
    except FileNotFoundError:
        console.print("[red]Error: alembic not found. Install with: pip install alembic[/red]")
        raise typer.Exit(1)


@app.command()
def upgrade(
    revision: str = typer.Option("head", "--revision", "-r", help="Target revision"),
) -> None:
    """
    Upgrade database to a revision.

    Examples:
        cli_typer_example.py db upgrade                  # Upgrade to latest
        cli_typer_example.py db upgrade --revision head   # Upgrade to latest
        cli_typer_example.py db upgrade -r abc123         # Upgrade to specific revision
    """
    _check_alembic()
    console.print(f"[bold]Upgrading database to revision: {revision}[/bold]\n")
    _run_alembic(["upgrade", revision])
    console.print("\n[green]Upgrade completed[/green]")


@app.command()
def downgrade(
    revision: str = typer.Option(..., "--revision", "-r", help="Target revision"),
) -> None:
    """
    Downgrade database to a revision.

    Examples:
        cli_typer_example.py db downgrade --revision -1       # Downgrade one revision
        cli_typer_example.py db downgrade -r abc123            # Downgrade to specific revision
        cli_typer_example.py db downgrade --revision base      # Downgrade to initial state
    """
    _check_alembic()
    console.print(f"[bold]Downgrading database to revision: {revision}[/bold]\n")
    _run_alembic(["downgrade", revision])
    console.print("\n[green]Downgrade completed[/green]")


@app.command()
def current() -> None:
    """
    Show current database revision.

    Examples:
        cli_typer_example.py db current
    """
    _check_alembic()
    console.print("[bold]Current database revision:[/bold]\n")
    _run_alembic(["current"])


@app.command()
def history() -> None:
    """
    Show migration history.

    Examples:
        cli_typer_example.py db history
    """
    _check_alembic()
    console.print("[bold]Migration history:[/bold]\n")
    _run_alembic(["history", "--verbose"])


@app.command()
def generate(
    message: str = typer.Option(..., "--message", "-m", help="Migration message"),
) -> None:
    """
    Auto-generate a new migration from model changes.

    Examples:
        cli_typer_example.py db generate -m "add users table"
        cli_typer_example.py db generate --message "add email column"
    """
    _check_alembic()
    console.print(f"[bold]Generating migration: {message}[/bold]\n")
    _run_alembic(["revision", "--autogenerate", "-m", message])
    console.print("\n[green]Migration generated[/green]")


@app.command()
def revision(
    message: str = typer.Option(..., "--message", "-m", help="Migration message"),
) -> None:
    """
    Create a new empty migration file.

    Examples:
        cli_typer_example.py db revision -m "manual migration"
    """
    _check_alembic()
    console.print(f"[bold]Creating migration: {message}[/bold]\n")
    _run_alembic(["revision", "-m", message])
    console.print("\n[green]Migration created[/green]")
