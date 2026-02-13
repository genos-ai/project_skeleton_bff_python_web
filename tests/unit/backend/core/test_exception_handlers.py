"""
Unit Tests for Exception Handlers.

Tests the exception handler functions in isolation.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import Request
from fastapi.exceptions import RequestValidationError

from modules.backend.core.exception_handlers import (
    application_error_handler,
    validation_error_handler,
    unhandled_exception_handler,
    EXCEPTION_STATUS_MAP,
    _get_request_id,
)
from modules.backend.core.exceptions import (
    ApplicationError,
    NotFoundError,
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    RateLimitError,
    DatabaseError,
    ExternalServiceError,
)


class TestExceptionStatusMapping:
    """Tests for exception to HTTP status code mapping."""

    def test_not_found_maps_to_404(self):
        """NotFoundError should map to 404."""
        assert EXCEPTION_STATUS_MAP[NotFoundError] == 404

    def test_validation_maps_to_400(self):
        """ValidationError should map to 400."""
        assert EXCEPTION_STATUS_MAP[ValidationError] == 400

    def test_authentication_maps_to_401(self):
        """AuthenticationError should map to 401."""
        assert EXCEPTION_STATUS_MAP[AuthenticationError] == 401

    def test_authorization_maps_to_403(self):
        """AuthorizationError should map to 403."""
        assert EXCEPTION_STATUS_MAP[AuthorizationError] == 403

    def test_conflict_maps_to_409(self):
        """ConflictError should map to 409."""
        assert EXCEPTION_STATUS_MAP[ConflictError] == 409

    def test_rate_limit_maps_to_429(self):
        """RateLimitError should map to 429."""
        assert EXCEPTION_STATUS_MAP[RateLimitError] == 429

    def test_external_service_maps_to_502(self):
        """ExternalServiceError should map to 502."""
        assert EXCEPTION_STATUS_MAP[ExternalServiceError] == 502

    def test_database_maps_to_503(self):
        """DatabaseError should map to 503."""
        assert EXCEPTION_STATUS_MAP[DatabaseError] == 503


class TestGetRequestId:
    """Tests for request ID extraction."""

    def test_extracts_from_request_state(self):
        """Should extract request_id from request.state."""
        request = MagicMock(spec=Request)
        request.state.request_id = "state-123"
        request.headers = {}

        result = _get_request_id(request)

        assert result == "state-123"

    def test_extracts_from_header(self):
        """Should extract request_id from x-request-id header."""
        request = MagicMock(spec=Request)
        # Simulate no request_id in state
        del request.state.request_id
        request.headers = {"x-request-id": "header-456"}

        result = _get_request_id(request)

        assert result == "header-456"

    def test_returns_none_when_not_present(self):
        """Should return None when no request_id available."""
        request = MagicMock(spec=Request)
        del request.state.request_id
        request.headers = {}

        result = _get_request_id(request)

        assert result is None


class TestApplicationErrorHandler:
    """Tests for application_error_handler."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/test"
        request.method = "GET"
        request.headers = {"x-request-id": "test-123"}
        del request.state.request_id
        return request

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, mock_request):
        """NotFoundError should return 404 response."""
        exc = NotFoundError("User not found")

        response = await application_error_handler(mock_request, exc)

        assert response.status_code == 404
        body = response.body.decode()
        assert "RES_NOT_FOUND" in body
        assert "User not found" in body

    @pytest.mark.asyncio
    async def test_authentication_returns_401(self, mock_request):
        """AuthenticationError should return 401 response."""
        exc = AuthenticationError("Invalid token")

        response = await application_error_handler(mock_request, exc)

        assert response.status_code == 401
        body = response.body.decode()
        assert "AUTH_UNAUTHORIZED" in body

    @pytest.mark.asyncio
    async def test_validation_includes_details(self, mock_request):
        """ValidationError should include details in response."""
        exc = ValidationError(
            "Validation failed",
            details={"email": "Invalid email format"},
        )

        response = await application_error_handler(mock_request, exc)

        assert response.status_code == 400
        body = response.body.decode()
        assert "VAL_VALIDATION_ERROR" in body
        assert "Invalid email format" in body

    @pytest.mark.asyncio
    async def test_response_includes_request_id(self, mock_request):
        """Response should include request_id in metadata."""
        exc = NotFoundError("Not found")

        response = await application_error_handler(mock_request, exc)

        body = response.body.decode()
        assert "test-123" in body

    @pytest.mark.asyncio
    async def test_unknown_application_error_returns_500(self, mock_request):
        """Unknown ApplicationError subclass should return 500."""
        # Create a custom exception not in the mapping
        exc = ApplicationError("Unknown error", code="CUSTOM_ERROR")

        response = await application_error_handler(mock_request, exc)

        assert response.status_code == 500


class TestValidationErrorHandler:
    """Tests for validation_error_handler."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/users"
        request.method = "POST"
        request.headers = {}
        del request.state.request_id
        return request

    @pytest.mark.asyncio
    async def test_returns_422(self, mock_request):
        """Request validation error should return 422."""
        # Create a mock RequestValidationError
        exc = MagicMock(spec=RequestValidationError)
        exc.errors.return_value = [
            {
                "loc": ("body", "email"),
                "msg": "field required",
                "type": "value_error.missing",
            }
        ]

        response = await validation_error_handler(mock_request, exc)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_includes_field_errors(self, mock_request):
        """Response should include field-level error details."""
        exc = MagicMock(spec=RequestValidationError)
        exc.errors.return_value = [
            {
                "loc": ("body", "email"),
                "msg": "invalid email",
                "type": "value_error",
            },
            {
                "loc": ("body", "age"),
                "msg": "must be positive",
                "type": "value_error",
            },
        ]

        response = await validation_error_handler(mock_request, exc)

        body = response.body.decode()
        assert "VAL_REQUEST_INVALID" in body
        assert "body.email" in body
        assert "body.age" in body


class TestUnhandledExceptionHandler:
    """Tests for unhandled_exception_handler."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/crash"
        request.method = "GET"
        request.headers = {}
        del request.state.request_id
        return request

    @pytest.mark.asyncio
    async def test_returns_500(self, mock_request):
        """Unhandled exception should return 500."""
        exc = RuntimeError("Something went wrong")

        response = await unhandled_exception_handler(mock_request, exc)

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_hides_internal_details(self, mock_request):
        """Response should not expose internal error details."""
        exc = RuntimeError("Database connection string: postgres://user:pass@host")

        response = await unhandled_exception_handler(mock_request, exc)

        body = response.body.decode()
        assert "postgres://" not in body
        assert "pass@host" not in body
        assert "SYS_INTERNAL_ERROR" in body
        assert "unexpected error" in body.lower()
