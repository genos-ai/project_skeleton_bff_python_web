"""
CLI Commands.

Organized by domain/feature area.
"""

from modules.cli.commands.db import app as db_app
from modules.cli.commands.health import app as health_app
from modules.cli.commands.server import app as server_app
from modules.cli.commands.system import app as system_app
from modules.cli.commands.test import app as test_app

__all__ = [
    "db_app",
    "health_app",
    "server_app",
    "system_app",
    "test_app",
]
