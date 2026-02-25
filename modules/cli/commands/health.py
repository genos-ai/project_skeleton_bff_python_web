"""
Health Check Commands.

Commands for checking backend health and status.
"""

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from modules.cli.client import get_api_client

app = typer.Typer(help="Health check commands")
console = Console()


@app.command()
def status(
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show detailed status"),
) -> None:
    """
    Check backend health status (requires running server).

    Shows basic health or detailed component status.

    Examples:
        cli_typer_example.py health status
        cli_typer_example.py health status -d
    """
    asyncio.run(_status(detailed))


async def _status(detailed: bool) -> None:
    """Async implementation of status command."""
    client = get_api_client()

    try:
        if detailed:
            response = await client.get("/health/detailed")
        else:
            response = await client.get("/health/ready")

        if response.status_code == 200:
            data = response.json()
            _display_health(data, detailed)
        elif response.status_code == 503:
            data = response.json()
            _display_health(data, detailed)
            raise typer.Exit(1)
        else:
            console.print(f"[red]Unexpected response: {response.status_code}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        if "Connection refused" in str(e) or "ConnectError" in str(e):
            console.print("[red]Error: Cannot connect to backend[/red]")
            console.print("[dim]Is the server running? Start with: cli_typer_example.py server start[/dim]")
        else:
            console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    finally:
        await client.close()


def _display_health(data: dict, detailed: bool) -> None:
    """Display health check results."""
    status = data.get("status", "unknown")
    status_color = "green" if status == "healthy" else "red" if status == "unhealthy" else "yellow"

    if detailed and "checks" in data:
        # Detailed view with table
        table = Table(title="Health Status", show_header=True)
        table.add_column("Component", style="cyan")
        table.add_column("Status")
        table.add_column("Details")

        checks = data.get("checks", {})
        for component, check_data in checks.items():
            check_status = check_data.get("status", "unknown")
            color = "green" if check_status == "healthy" else "red" if check_status == "unhealthy" else "yellow"

            details = []
            if "latency_ms" in check_data:
                details.append(f"latency: {check_data['latency_ms']}ms")
            if "error" in check_data:
                details.append(f"error: {check_data['error']}")

            table.add_row(
                component,
                f"[{color}]{check_status}[/{color}]",
                ", ".join(details) if details else "-",
            )

        console.print(table)

        # Application info if present
        if "application" in data:
            app_info = data["application"]
            console.print(f"\n[dim]Application: {app_info.get('name', 'N/A')} v{app_info.get('version', 'N/A')}[/dim]")
            console.print(f"[dim]Environment: {app_info.get('environment', 'N/A')}[/dim]")

    else:
        # Simple view
        console.print(Panel(
            f"[{status_color}]{status.upper()}[/{status_color}]",
            title="Backend Status",
        ))


@app.command()
def ping() -> None:
    """
    Simple ping to check if backend is reachable.

    Returns success if backend responds, failure otherwise.

    Examples:
        cli_typer_example.py health ping
    """
    asyncio.run(_ping())


async def _ping() -> None:
    """Async implementation of ping command."""
    client = get_api_client()

    try:
        response = await client.get("/health")

        if response.status_code == 200:
            console.print("[green]✓ Backend is reachable[/green]")
        else:
            console.print(f"[yellow]Backend responded with status {response.status_code}[/yellow]")

    except Exception as e:
        if "Connection refused" in str(e) or "ConnectError" in str(e):
            console.print("[red]✗ Backend is not reachable[/red]")
        else:
            console.print(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)

    finally:
        await client.close()


@app.command()
def check() -> None:
    """
    Check application health locally (imports, config).

    Does NOT require running server. Tests that modules load correctly.

    Examples:
        cli_typer_example.py health check
    """
    console.print("[bold]Checking application health...[/bold]\n")

    checks = []

    # Check 1: Core imports
    try:
        from modules.backend.core.config import get_settings, get_app_config
        from modules.backend.core.logging import get_logger
        from modules.backend.core.exceptions import ApplicationError
        checks.append(("Core imports", True, None))
    except Exception as e:
        checks.append(("Core imports", False, str(e)))

    # Check 2: Configuration loading
    try:
        from modules.backend.core.config import get_app_config
        app_config = get_app_config()
        app_name = app_config.application.get("name")
        checks.append(("YAML configuration", True, f"App: {app_name}"))
    except Exception as e:
        checks.append(("YAML configuration", False, str(e)))

    # Check 3: Secrets (.env)
    try:
        from modules.backend.core.config import get_settings
        get_settings()
        checks.append(("Secrets (.env)", True, None))
    except Exception as e:
        checks.append(("Secrets (.env)", False, str(e)))

    # Check 4: FastAPI app
    try:
        from modules.backend.main import get_app
        fastapi_app = get_app()
        checks.append(("FastAPI application", True, f"Title: {fastapi_app.title}"))
    except Exception as e:
        checks.append(("FastAPI application", False, str(e)))

    # Check 5: Database models
    try:
        from modules.backend.models.base import Base, TimestampMixin, UUIDMixin
        checks.append(("Database models", True, None))
    except Exception as e:
        checks.append(("Database models", False, str(e)))

    # Check 6: Schemas
    try:
        from modules.backend.schemas.base import ApiResponse, ErrorResponse
        checks.append(("API schemas", True, None))
    except Exception as e:
        checks.append(("API schemas", False, str(e)))

    # Display results
    table = Table(title="Health Check Results", show_header=True)
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    all_passed = True
    for name, passed, detail in checks:
        status = "[green]✓ PASS[/green]" if passed else "[red]✗ FAIL[/red]"
        table.add_row(name, status, detail or "-")
        if not passed:
            all_passed = False

    console.print(table)

    if all_passed:
        console.print("\n[green]All checks passed![/green]")
    else:
        console.print("\n[yellow]Some checks failed. See details above.[/yellow]")
        console.print("[dim]Note: Environment settings require config/.env to be configured.[/dim]")
        raise typer.Exit(1)
