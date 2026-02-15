"""
System Commands.

Commands for system information and configuration.
"""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from modules.cli.client import get_api_client

app = typer.Typer(help="System information commands")
console = Console()


@app.command()
def info() -> None:
    """
    Display application information.

    Shows app name, version, and configuration summary.
    """
    try:
        from modules.backend.core.config import get_app_config

        app_config = get_app_config()

        console.print(Panel(
            f"[bold]{app_config.application.get('name', 'N/A')}[/bold]\n"
            f"Version: {app_config.application.get('version', 'N/A')}\n"
            f"Description: {app_config.application.get('description', 'N/A')}",
            title="Application Info",
        ))

    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def config(
    section: Optional[str] = typer.Argument(None, help="Config section to show (application, database, logging, features)"),
) -> None:
    """
    Display configuration settings.

    Shows all configuration or a specific section.
    """
    try:
        from modules.backend.core.config import get_app_config

        app_config = get_app_config()

        sections = {
            "application": app_config.application,
            "database": app_config.database,
            "logging": app_config.logging,
            "features": app_config.features,
        }

        if section:
            if section not in sections:
                console.print(f"[red]Unknown section: {section}[/red]")
                console.print(f"Available sections: {', '.join(sections.keys())}")
                raise typer.Exit(1)

            _display_config_section(section, sections[section])
        else:
            for name, data in sections.items():
                _display_config_section(name, data)
                console.print()

    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        raise typer.Exit(1)


def _display_config_section(name: str, data: dict) -> None:
    """Display a configuration section as a tree."""
    tree = Tree(f"[bold cyan]{name}[/bold cyan]")

    def add_items(parent: Tree, items: dict, indent: int = 0) -> None:
        for key, value in items.items():
            if isinstance(value, dict):
                branch = parent.add(f"[cyan]{key}[/cyan]")
                add_items(branch, value, indent + 1)
            else:
                parent.add(f"[cyan]{key}[/cyan]: {value}")

    add_items(tree, data)
    console.print(tree)


@app.command()
def env() -> None:
    """
    Display environment settings (non-sensitive).

    Shows application environment, debug mode, etc.
    """
    try:
        from modules.backend.core.config import get_settings

        settings = get_settings()

        table = Table(title="Environment Settings", show_header=True)
        table.add_column("Setting", style="cyan")
        table.add_column("Value")

        # Only show non-sensitive settings
        table.add_row("App Name", settings.app_name)
        table.add_row("Environment", settings.app_env)
        table.add_row("Debug Mode", str(settings.app_debug))
        table.add_row("Log Level", settings.app_log_level)
        table.add_row("Server Host", settings.server_host)
        table.add_row("Server Port", str(settings.server_port))

        console.print(table)

    except Exception as e:
        console.print(f"[yellow]Warning: Could not load environment settings[/yellow]")
        console.print(f"[dim]Error: {e}[/dim]")
        console.print("\n[dim]Ensure config/.env is configured.[/dim]")


@app.command()
def version() -> None:
    """
    Display version information.
    """
    try:
        from modules.backend.core.config import get_app_config

        app_config = get_app_config()
        version = app_config.application.get("version", "unknown")

        console.print(f"[bold]{version}[/bold]")

    except Exception:
        console.print("[yellow]unknown[/yellow]")
