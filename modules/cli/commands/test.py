"""
Test Commands.

Commands for running the test suite.
"""

import subprocess
import sys
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(help="Test suite commands")
console = Console()


@app.command()
def run(
    test_type: str = typer.Option(
        "all",
        "--type", "-t",
        help="Test type: all, unit, integration, e2e",
    ),
    coverage: bool = typer.Option(False, "--coverage", "-c", help="Run with coverage"),
    verbose: bool = typer.Option(True, "--verbose/--quiet", "-v/-q", help="Verbose output"),
    pattern: Optional[str] = typer.Option(None, "--pattern", "-k", help="Test name pattern to match"),
    fail_fast: bool = typer.Option(False, "--fail-fast", "-x", help="Stop on first failure"),
) -> None:
    """
    Run the test suite.

    Examples:
        cli_typer.py test run                         # Run all tests
        cli_typer.py test run --type unit              # Run unit tests only
        cli_typer.py test run -t integration           # Run integration tests
        cli_typer.py test run --type unit --coverage   # Unit tests with coverage
        cli_typer.py test run -k "test_health"         # Run tests matching pattern
        cli_typer.py test run --fail-fast              # Stop on first failure
    """
    cmd = [sys.executable, "-m", "pytest"]

    # Select test directory
    if test_type == "unit":
        cmd.append("tests/unit")
    elif test_type == "integration":
        cmd.append("tests/integration")
    elif test_type == "e2e":
        cmd.append("tests/e2e")
    else:
        cmd.append("tests/")

    # Options
    if verbose:
        cmd.append("-v")

    if coverage:
        cmd.extend(["--cov=modules/backend", "--cov-report=term-missing"])

    if pattern:
        cmd.extend(["-k", pattern])

    if fail_fast:
        cmd.append("-x")

    console.print(f"[bold]Running tests:[/bold] {test_type}")
    if coverage:
        console.print("[dim]Coverage enabled[/dim]")
    console.print(f"[dim]Command: {' '.join(cmd)}[/dim]\n")

    try:
        result = subprocess.run(cmd)
        raise typer.Exit(result.returncode)
    except FileNotFoundError:
        console.print("[red]Error: pytest not found. Install with: pip install pytest[/red]")
        raise typer.Exit(1)


@app.command()
def unit(
    coverage: bool = typer.Option(False, "--coverage", "-c", help="Run with coverage"),
    pattern: Optional[str] = typer.Option(None, "--pattern", "-k", help="Test name pattern"),
) -> None:
    """
    Run unit tests (shortcut).

    Examples:
        cli_typer.py test unit
        cli_typer.py test unit --coverage
    """
    cmd = [sys.executable, "-m", "pytest", "tests/unit", "-v"]

    if coverage:
        cmd.extend(["--cov=modules/backend", "--cov-report=term-missing"])

    if pattern:
        cmd.extend(["-k", pattern])

    console.print("[bold]Running unit tests[/bold]\n")

    try:
        result = subprocess.run(cmd)
        raise typer.Exit(result.returncode)
    except FileNotFoundError:
        console.print("[red]Error: pytest not found[/red]")
        raise typer.Exit(1)


@app.command()
def integration(
    coverage: bool = typer.Option(False, "--coverage", "-c", help="Run with coverage"),
) -> None:
    """
    Run integration tests (shortcut).

    Examples:
        cli_typer.py test integration
    """
    cmd = [sys.executable, "-m", "pytest", "tests/integration", "-v"]

    if coverage:
        cmd.extend(["--cov=modules/backend", "--cov-report=term-missing"])

    console.print("[bold]Running integration tests[/bold]\n")

    try:
        result = subprocess.run(cmd)
        raise typer.Exit(result.returncode)
    except FileNotFoundError:
        console.print("[red]Error: pytest not found[/red]")
        raise typer.Exit(1)
