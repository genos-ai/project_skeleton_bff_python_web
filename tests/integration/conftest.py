"""
Integration Test Fixtures.

Fixtures for integration tests - uses real database and services.
These fixtures build on the root conftest.py database fixtures.
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.database import get_db_session


# =============================================================================
# API Client Fixtures
# =============================================================================


@pytest.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Create a test client with database session override.

    The client uses the test database session, ensuring all API
    operations use the same session that gets rolled back after the test.

    Usage:
        async def test_health_endpoint(client: AsyncClient):
            response = await client.get("/health")
            assert response.status_code == 200
    """
    # Override the database session dependency
    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    # Patch get_settings BEFORE importing main to avoid module-level app creation
    # This is needed because main.py has `app = create_app()` at module level
    with patch("modules.backend.core.config.get_settings") as mock_config_settings, \
         patch("modules.backend.core.security.get_settings") as mock_security_settings:
        mock_settings = _create_mock_settings()
        mock_config_settings.return_value = mock_settings
        mock_security_settings.return_value = mock_settings

        from modules.backend.main import create_app

        app = create_app()
        app.dependency_overrides[get_db_session] = override_get_db_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client

        # Clear overrides
        app.dependency_overrides.clear()


@pytest.fixture
async def client_no_db() -> AsyncGenerator[AsyncClient, None]:
    """
    Create a test client without database dependency override.

    Use this for testing endpoints that don't require database access
    (e.g., health checks, static responses).

    Note: This requires mocking get_settings since no .env exists.
    """
    # Patch get_settings BEFORE importing main to avoid module-level app creation
    with patch("modules.backend.core.config.get_settings") as mock_config_settings, \
         patch("modules.backend.core.security.get_settings") as mock_security_settings:
        mock_settings = _create_mock_settings()
        mock_config_settings.return_value = mock_settings
        mock_security_settings.return_value = mock_settings

        from modules.backend.main import create_app

        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client


# =============================================================================
# Mock Settings Helper
# =============================================================================


def _create_mock_settings() -> Any:
    """Create a mock settings object for testing."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.app_name = "Test Application"
    settings.app_env = "test"
    settings.app_debug = True
    settings.app_log_level = "WARNING"
    settings.cors_origins = ["http://localhost:3000"]
    settings.server_host = "127.0.0.1"
    settings.server_port = 8000
    settings.jwt_secret = "test-secret-key"
    settings.jwt_algorithm = "HS256"
    settings.jwt_access_token_expire_minutes = 30
    settings.jwt_refresh_token_expire_days = 7
    return settings


# =============================================================================
# API Response Assertion Helpers
# =============================================================================


class ApiAssertions:
    """Helper class for API response assertions."""

    @staticmethod
    def assert_success(response: Any, expected_status: int = 200) -> dict[str, Any]:
        """
        Assert API response is successful.

        Args:
            response: httpx Response object
            expected_status: Expected HTTP status code

        Returns:
            Response JSON data

        Raises:
            AssertionError: If response is not successful
        """
        assert response.status_code == expected_status, (
            f"Expected status {expected_status}, got {response.status_code}: "
            f"{response.text}"
        )
        data = response.json()
        assert data.get("success") is True, f"Response not successful: {data}"
        return data

    @staticmethod
    def assert_error(
        response: Any,
        expected_status: int,
        expected_code: str | None = None,
    ) -> dict[str, Any]:
        """
        Assert API response is an error.

        Args:
            response: httpx Response object
            expected_status: Expected HTTP status code
            expected_code: Expected error code (optional)

        Returns:
            Response JSON data

        Raises:
            AssertionError: If response is not an error or codes don't match
        """
        assert response.status_code == expected_status, (
            f"Expected status {expected_status}, got {response.status_code}: "
            f"{response.text}"
        )
        data = response.json()
        assert data.get("success") is False, f"Response should be error: {data}"
        assert data.get("error") is not None, f"Missing error details: {data}"

        if expected_code:
            actual_code = data["error"].get("code")
            assert actual_code == expected_code, (
                f"Expected error code {expected_code}, got {actual_code}"
            )

        return data

    @staticmethod
    def assert_validation_error(
        response: Any,
        field: str | None = None,
    ) -> dict[str, Any]:
        """
        Assert API response is a validation error (422).

        Args:
            response: httpx Response object
            field: Expected field with validation error (optional)

        Returns:
            Response JSON data
        """
        data = ApiAssertions.assert_error(response, 422, "VAL_REQUEST_INVALID")

        if field:
            errors = data["error"].get("details", {}).get("validation_errors", [])
            fields = [e.get("field", "") for e in errors]
            assert any(field in f for f in fields), (
                f"Expected validation error for field '{field}', "
                f"got errors for: {fields}"
            )

        return data


@pytest.fixture
def api() -> ApiAssertions:
    """Provide API assertion helpers."""
    return ApiAssertions()


# =============================================================================
# Authentication Fixtures
# =============================================================================


@pytest.fixture
def auth_headers(test_settings: dict[str, Any]) -> dict[str, str]:
    """
    Provide authentication headers for API requests.

    Creates a valid JWT token for testing authenticated endpoints.

    Usage:
        async def test_protected_endpoint(client: AsyncClient, auth_headers: dict):
            response = await client.get("/api/v1/me", headers=auth_headers)
            assert response.status_code == 200
    """
    from modules.backend.core.security import create_access_token

    # Create a test token with mock user data
    token = create_access_token(
        data={"sub": "test-user-id", "email": "test@example.com"},
    )
    return {"Authorization": f"Bearer {token}"}
