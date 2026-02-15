"""
Interactive Shell Mode.

Provides a REPL-style interactive shell for the CLI client.
Uses Rich for output formatting and basic input handling.
"""

import asyncio
import shlex
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from modules.cli.client import close_api_client, get_api_client

console = Console()


class InteractiveShell:
    """
    Interactive shell for CLI commands.

    Provides a simple REPL with command history and help.

    Usage:
        shell = InteractiveShell()
        await shell.run()
    """

    def __init__(self) -> None:
        """Initialize the interactive shell."""
        self.running = False
        self.commands: dict[str, Callable] = {
            "help": self._cmd_help,
            "status": self._cmd_status,
            "ping": self._cmd_ping,
            "info": self._cmd_info,
            "config": self._cmd_config,
            "version": self._cmd_version,
            "clear": self._cmd_clear,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
        }

    async def run(self) -> None:
        """Run the interactive shell."""
        self.running = True

        console.print(Panel(
            "[bold]Interactive CLI Shell[/bold]\n"
            "Type [cyan]help[/cyan] for available commands, [cyan]quit[/cyan] to exit.",
            title="Welcome",
        ))
        console.print()

        while self.running:
            try:
                # Simple input prompt
                user_input = console.input("[bold cyan]>[/bold cyan] ").strip()

                if not user_input:
                    continue

                # Parse command and arguments
                parts = shlex.split(user_input)
                command = parts[0].lower()
                args = parts[1:]

                # Execute command
                if command in self.commands:
                    await self.commands[command](args)
                else:
                    console.print(f"[red]Unknown command: {command}[/red]")
                    console.print("Type [cyan]help[/cyan] for available commands.")

            except KeyboardInterrupt:
                console.print("\n[dim]Use 'quit' to exit[/dim]")
            except EOFError:
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        # Cleanup
        await close_api_client()
        console.print("[dim]Goodbye![/dim]")

    async def _cmd_help(self, args: list[str]) -> None:
        """Display help information."""
        table = Table(title="Available Commands", show_header=True)
        table.add_column("Command", style="cyan")
        table.add_column("Description")

        table.add_row("help", "Show this help message")
        table.add_row("status", "Check backend health status")
        table.add_row("status -d", "Show detailed health status")
        table.add_row("ping", "Ping the backend")
        table.add_row("info", "Show application information")
        table.add_row("config", "Show configuration")
        table.add_row("config <section>", "Show specific config section")
        table.add_row("version", "Show version")
        table.add_row("clear", "Clear the screen")
        table.add_row("quit / exit", "Exit the shell")

        console.print(table)

    async def _cmd_status(self, args: list[str]) -> None:
        """Check backend status."""
        from modules.cli.commands.health import _status

        detailed = "-d" in args or "--detailed" in args
        try:
            await _status(detailed)
        except SystemExit:
            pass  # Don't exit shell on command failure

    async def _cmd_ping(self, args: list[str]) -> None:
        """Ping the backend."""
        from modules.cli.commands.health import _ping

        try:
            await _ping()
        except SystemExit:
            pass

    async def _cmd_info(self, args: list[str]) -> None:
        """Show application info."""
        from modules.cli.commands.system import info

        try:
            info()
        except SystemExit:
            pass

    async def _cmd_config(self, args: list[str]) -> None:
        """Show configuration."""
        from modules.cli.commands.system import config

        section = args[0] if args else None
        try:
            config(section)
        except SystemExit:
            pass

    async def _cmd_version(self, args: list[str]) -> None:
        """Show version."""
        from modules.cli.commands.system import version

        version()

    async def _cmd_clear(self, args: list[str]) -> None:
        """Clear the screen."""
        console.clear()

    async def _cmd_quit(self, args: list[str]) -> None:
        """Exit the shell."""
        self.running = False


async def run_shell() -> None:
    """Run the interactive shell."""
    shell = InteractiveShell()
    await shell.run()
