"""Integration tests for enhanced health endpoints."""

from typing import Any

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_readiness_returns_without_crash(client_no_db: AsyncClient) -> None:
    """GET /health/ready should return 200 or 503 without crashing.

    In test environments without a real database, 503 is expected because
    the health check detects the DB as unhealthy. The exception handler
    wraps the response in the standard ErrorResponse envelope.
    """
    response = await client_no_db.get("/health/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    if response.status_code == 200:
        assert data.get("status") == "healthy"
    else:
        assert data.get("error") is not None or data.get("detail") is not None


@pytest.mark.asyncio
async def test_detailed_includes_pools_key(client_no_db: AsyncClient) -> None:
    """GET /health/detailed should include a 'pools' key in response."""
    response = await client_no_db.get("/health/detailed")
    data = response.json()
    assert "pools" in data
    assert isinstance(data["pools"], dict)


@pytest.mark.asyncio
async def test_detailed_returns_app_info(client_no_db: AsyncClient) -> None:
    """GET /health/detailed should include application info."""
    response = await client_no_db.get("/health/detailed")
    data = response.json()
    assert "application" in data
    app_info = data["application"]
    assert "name" in app_info
    assert "env" in app_info
    assert "version" in app_info


@pytest.mark.asyncio
async def test_liveness_always_healthy(client_no_db: AsyncClient) -> None:
    """GET /health should always return 200."""
    response = await client_no_db.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
