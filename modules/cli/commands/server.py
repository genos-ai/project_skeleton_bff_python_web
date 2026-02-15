"""
Server Commands.

Commands for starting and managing the application server, workers, and scheduler.
"""

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Server management commands")
console = Console()

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _get_settings():
    """Load settings with error handling."""
    try:
        from modules.backend.core.config import get_settings
        return get_settings()
    except Exception as e:
        console.print(f"[red]Error: Could not load settings.[/red]")
        console.print(f"[dim]Ensure config/.env exists and is configured.[/dim]")
        console.print(f"[dim]Error: {e}[/dim]")
        raise typer.Exit(1)


@app.command()
def start(
    host: str = typer.Option(None, "--host", "-h", help="Server host"),
    port: int = typer.Option(None, "--port", "-p", help="Server port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
) -> None:
    """
    Start the FastAPI development server.

    Examples:
        cli.py server start
        cli.py server start --reload
        cli.py server start --host 0.0.0.0 --port 8080
    """
    settings = _get_settings()

    server_host = host or settings.server_host
    server_port = port or settings.server_port

    cmd = [
        sys.executable, "-m", "uvicorn",
        "modules.backend.main:app",
        "--host", server_host,
        "--port", str(server_port),
    ]

    if reload:
        cmd.append("--reload")

    console.print(f"[bold]Starting server at http://{server_host}:{server_port}[/bold]")
    if reload:
        console.print("[dim]Auto-reload enabled[/dim]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped[/dim]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Server failed to start (exit code: {e.returncode})[/red]")
        raise typer.Exit(e.returncode)


@app.command()
def worker(
    workers: int = typer.Option(1, "--workers", "-w", help="Number of worker processes"),
) -> None:
    """
    Start the Taskiq background task worker.

    Examples:
        cli.py server worker
        cli.py server worker --workers 4
    """
    settings = _get_settings()

    # Verify Redis URL
    try:
        redis_url = settings.redis_url
        console.print(f"[dim]Redis: {redis_url.split('@')[-1]}[/dim]")
    except Exception as e:
        console.print("[red]Error: REDIS_URL not configured in config/.env[/red]")
        raise typer.Exit(1)

    cmd = [
        sys.executable, "-m", "taskiq",
        "worker",
        "modules.backend.tasks.broker:broker",
        "--workers", str(workers),
    ]

    console.print(f"[bold]Starting Taskiq worker with {workers} worker(s)[/bold]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        console.print("\n[dim]Worker stopped[/dim]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Worker failed to start (exit code: {e.returncode})[/red]")
        raise typer.Exit(e.returncode)


@app.command()
def scheduler() -> None:
    """
    Start the Taskiq task scheduler for cron-based tasks.

    WARNING: Run only ONE scheduler instance to avoid duplicate task execution.

    Examples:
        cli.py server scheduler
    """
    settings = _get_settings()

    # Verify Redis URL
    try:
        redis_url = settings.redis_url
        console.print(f"[dim]Redis: {redis_url.split('@')[-1]}[/dim]")
    except Exception as e:
        console.print("[red]Error: REDIS_URL not configured in config/.env[/red]")
        raise typer.Exit(1)

    # Register scheduled tasks
    try:
        from modules.backend.tasks.scheduled import register_scheduled_tasks, SCHEDULED_TASKS
        register_scheduled_tasks()

        console.print("[bold]Registered scheduled tasks:[/bold]")
        for task_name, config in SCHEDULED_TASKS.items():
            schedule = config["schedule"][0].get("cron", "N/A")
            console.print(f"  [cyan]{task_name}[/cyan]: {schedule}")
        console.print()
    except Exception as e:
        console.print(f"[red]Error registering tasks: {e}[/red]")
        raise typer.Exit(1)

    cmd = [
        sys.executable, "-m", "taskiq",
        "scheduler",
        "modules.backend.tasks.scheduler:scheduler",
    ]

    console.print("[bold]Starting Taskiq scheduler[/bold]")
    console.print("[yellow]WARNING: Run only ONE scheduler instance[/yellow]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        console.print("\n[dim]Scheduler stopped[/dim]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Scheduler failed to start (exit code: {e.returncode})[/red]")
        raise typer.Exit(e.returncode)
