"""
Unit Tests for Request Context Middleware.

Tests the RequestContextMiddleware functionality including:
- Request ID generation and propagation
- Source extraction from X-Frontend-ID header
- Response timing headers
- Structlog context binding
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from starlette.requests import Request
from starlette.responses import Response


class TestRequestContextMiddleware:
    """Tests for RequestContextMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        from modules.backend.core.middleware import RequestContextMiddleware

        mock_app = MagicMock()
        return RequestContextMiddleware(mock_app)

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.method = "GET"
        request.url = MagicMock()
        request.url.path = "/api/v1/test"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.state = MagicMock()
        return request

    # -------------------------------------------------------------------------
    # Source (X-Frontend-ID) Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_extracts_source_web(self, middleware, mock_request):
        """Should extract source when X-Frontend-ID header is 'web'."""
        mock_request.headers = {"X-Frontend-ID": "web"}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            assert request.state.source == "web"
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            await middleware.dispatch(mock_request, call_next)

    @pytest.mark.asyncio
    async def test_extracts_source_cli(self, middleware, mock_request):
        """Should extract source when X-Frontend-ID header is 'cli'."""
        mock_request.headers = {"X-Frontend-ID": "cli"}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            assert request.state.source == "cli"
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            await middleware.dispatch(mock_request, call_next)

    @pytest.mark.asyncio
    async def test_extracts_source_telegram(self, middleware, mock_request):
        """Should extract source when X-Frontend-ID header is 'telegram'."""
        mock_request.headers = {"X-Frontend-ID": "telegram"}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            assert request.state.source == "telegram"
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            await middleware.dispatch(mock_request, call_next)

    @pytest.mark.asyncio
    async def test_source_defaults_to_unknown_when_header_missing(self, middleware, mock_request):
        """Should set source to 'unknown' when X-Frontend-ID header is missing."""
        mock_request.headers = {}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            assert request.state.source == "unknown"
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            await middleware.dispatch(mock_request, call_next)

    @pytest.mark.asyncio
    async def test_unrecognized_source_defaults_to_unknown(self, middleware, mock_request):
        """Should default unrecognized X-Frontend-ID values to 'unknown'."""
        mock_request.headers = {"X-Frontend-ID": "custom-client"}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            assert request.state.source == "unknown"
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            await middleware.dispatch(mock_request, call_next)

    @pytest.mark.asyncio
    async def test_source_case_insensitive(self, middleware, mock_request):
        """Should handle X-Frontend-ID header case-insensitively."""
        mock_request.headers = {"X-Frontend-ID": "WEB"}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            assert request.state.source == "web"
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            await middleware.dispatch(mock_request, call_next)

    @pytest.mark.asyncio
    async def test_source_bound_to_structlog_when_present(self, middleware, mock_request):
        """Should bind source to structlog context when X-Frontend-ID is provided."""
        mock_request.headers = {"X-Frontend-ID": "cli"}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars") as mock_ctx:
            await middleware.dispatch(mock_request, call_next)

            call_kwargs = mock_ctx.bind_contextvars.call_args[1]
            assert call_kwargs["source"] == "cli"

    @pytest.mark.asyncio
    async def test_source_bound_as_unknown_when_header_missing(self, middleware, mock_request):
        """Should bind source as 'unknown' in structlog context when header is missing."""
        mock_request.headers = {}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars") as mock_ctx:
            await middleware.dispatch(mock_request, call_next)

            call_kwargs = mock_ctx.bind_contextvars.call_args[1]
            assert call_kwargs["source"] == "unknown"

    # -------------------------------------------------------------------------
    # X-Request-ID Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_generates_request_id_when_not_provided(self, middleware, mock_request):
        """Should generate a UUID request ID when X-Request-ID header is missing."""
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            assert hasattr(request.state, "request_id")
            assert request.state.request_id is not None
            assert len(request.state.request_id) == 36
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            response = await middleware.dispatch(mock_request, call_next)

        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 36

    @pytest.mark.asyncio
    async def test_uses_provided_request_id(self, middleware, mock_request):
        """Should use X-Request-ID header when provided."""
        provided_id = "custom-request-id-123"
        mock_request.headers = {"X-Request-ID": provided_id}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            assert request.state.request_id == provided_id
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["X-Request-ID"] == provided_id

    # -------------------------------------------------------------------------
    # X-Response-Time Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_adds_response_time_header(self, middleware, mock_request):
        """Should add X-Response-Time header with duration."""
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            response = await middleware.dispatch(mock_request, call_next)

        assert "X-Response-Time" in response.headers
        assert response.headers["X-Response-Time"].endswith("ms")

    # -------------------------------------------------------------------------
    # Request State Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sets_start_time_on_request_state(self, middleware, mock_request):
        """Should set start_time on request.state."""
        mock_response = Response(content="OK", status_code=200)
        captured_start_time = None

        async def call_next(request):
            nonlocal captured_start_time
            captured_start_time = request.state.start_time
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            await middleware.dispatch(mock_request, call_next)

        assert captured_start_time is not None
        assert isinstance(captured_start_time, datetime)
        assert captured_start_time.tzinfo is None

    # -------------------------------------------------------------------------
    # Structlog Context Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_binds_context_to_structlog(self, middleware, mock_request):
        """Should bind request context to structlog contextvars."""
        mock_request.headers = {"X-Frontend-ID": "web"}
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars") as mock_ctx:
            await middleware.dispatch(mock_request, call_next)

            mock_ctx.clear_contextvars.assert_called()
            mock_ctx.bind_contextvars.assert_called_once()
            call_kwargs = mock_ctx.bind_contextvars.call_args[1]
            assert "request_id" in call_kwargs
            assert call_kwargs["source"] == "web"
            assert call_kwargs["method"] == "GET"
            assert call_kwargs["path"] == "/api/v1/test"

    @pytest.mark.asyncio
    async def test_clears_context_after_request(self, middleware, mock_request):
        """Should clear structlog context after request completes."""
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars") as mock_ctx:
            await middleware.dispatch(mock_request, call_next)

            assert mock_ctx.clear_contextvars.call_count == 2

    @pytest.mark.asyncio
    async def test_clears_context_on_exception(self, middleware, mock_request):
        """Should clear structlog context even when exception occurs."""

        async def call_next(request):
            raise ValueError("Test error")

        with patch("modules.backend.core.middleware.structlog.contextvars") as mock_ctx:
            with pytest.raises(ValueError):
                await middleware.dispatch(mock_request, call_next)

            assert mock_ctx.clear_contextvars.call_count == 2

    @pytest.mark.asyncio
    async def test_reraises_exception(self, middleware, mock_request):
        """Should re-raise exceptions after logging."""

        async def call_next(request):
            raise RuntimeError("Something went wrong")

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            with pytest.raises(RuntimeError, match="Something went wrong"):
                await middleware.dispatch(mock_request, call_next)

    @pytest.mark.asyncio
    async def test_handles_missing_client(self, middleware, mock_request):
        """Should handle requests without client info."""
        mock_request.client = None
        mock_response = Response(content="OK", status_code=200)

        async def call_next(request):
            return mock_response

        with patch("modules.backend.core.middleware.structlog.contextvars"):
            response = await middleware.dispatch(mock_request, call_next)
            assert response.status_code == 200
