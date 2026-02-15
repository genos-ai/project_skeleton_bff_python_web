"""
CLI Client Module.

Interactive command-line client built with Typer for communicating
with the backend API.

Architecture:
- CLI is a thin presentation layer
- All business logic lives in the backend
- CLI calls backend via HTTP (httpx)
- Sends X-Frontend-ID: cli header for log routing

Usage:
    python cli.py --help
    python cli.py status
    python cli.py health
    python cli.py shell  # Interactive mode
"""
