"""Unit tests for CLI HTTP client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from modules.cli.client import APIClient, close_api_client, get_api_client


class TestAPIClient:
    """Tests for APIClient class."""

    @pytest.fixture
    def client(self) -> APIClient:
        """Create a test client."""
        return APIClient(base_url="http://test:8000")

    @pytest.mark.asyncio
    async def test_client_initialization(self, client: APIClient) -> None:
        """Test client initializes with correct base URL."""
        assert client.base_url == "http://test:8000"
        assert client.timeout == 30.0

    @pytest.mark.asyncio
    async def test_client_strips_trailing_slash(self) -> None:
        """Test client strips trailing slash from base URL."""
        client = APIClient(base_url="http://test:8000/")
        assert client.base_url == "http://test:8000"

    @pytest.mark.asyncio
    async def test_get_request(self, client: APIClient) -> None:
        """Test GET request."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            response = await client.get("/health")

            assert response.status_code == 200

        await client.close()

    @pytest.mark.asyncio
    async def test_post_request(self, client: APIClient) -> None:
        """Test POST request."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201

        with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            response = await client.post("/api/v1/items", json={"name": "test"})

            assert response.status_code == 201

        await client.close()

    @pytest.mark.asyncio
    async def test_client_includes_frontend_header(self, client: APIClient) -> None:
        """Test client includes X-Frontend-ID header."""
        # Access internal client to check headers
        internal_client = await client._get_client()
        assert internal_client.headers.get("X-Frontend-ID") == "cli"
        await client.close()

    @pytest.mark.asyncio
    async def test_close_client(self, client: APIClient) -> None:
        """Test client closes properly."""
        # Create internal client
        await client._get_client()
        assert client._client is not None

        # Close
        await client.close()
        assert client._client is None


class TestModuleLevelFunctions:
    """Tests for module-level client functions."""

    @pytest.mark.asyncio
    async def test_get_api_client_singleton(self) -> None:
        """Test get_api_client returns singleton."""
        # Reset module state
        import modules.cli.client as client_module
        client_module._client = None

        client1 = get_api_client()
        client2 = get_api_client()

        assert client1 is client2

        # Cleanup
        await close_api_client()

    @pytest.mark.asyncio
    async def test_close_api_client(self) -> None:
        """Test close_api_client cleans up."""
        import modules.cli.client as client_module
        client_module._client = None

        # Create client
        client = get_api_client()
        assert client_module._client is not None

        # Close
        await close_api_client()
        assert client_module._client is None
