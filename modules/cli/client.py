"""
HTTP Client for CLI.

Provides async HTTP client for communicating with the backend API.
All requests include X-Frontend-ID: cli header for log routing.
"""

from typing import Any

import httpx

from modules.backend.core.config import get_settings
from modules.backend.core.logging import get_logger, log_with_source

logger = get_logger(__name__)

# Default timeout for API calls
DEFAULT_TIMEOUT = 30.0


class APIClient:
    """
    HTTP client for backend API communication.

    Features:
    - Automatic base URL from settings
    - X-Frontend-ID header for log routing
    - Structured logging of requests/responses
    - Error handling with context

    Usage:
        client = APIClient()
        response = await client.get("/health")
        response = await client.post("/api/v1/users", json={"name": "test"})
    """

    def __init__(self, base_url: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        """
        Initialize the API client.

        Args:
            base_url: Backend API base URL. If None, reads from settings.
            timeout: Request timeout in seconds.
        """
        if base_url is None:
            try:
                settings = get_settings()
                base_url = f"http://{settings.server_host}:{settings.server_port}"
            except Exception:
                # Default for development
                base_url = "http://localhost:8000"

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"X-Frontend-ID": "cli"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Make an HTTP request to the backend.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., /health, /api/v1/users)
            **kwargs: Additional arguments for httpx

        Returns:
            httpx.Response

        Raises:
            httpx.HTTPError: On request failure
        """
        client = await self._get_client()

        log_with_source(
            logger,
            "cli",
            "debug",
            "API request",
            method=method,
            path=path,
        )

        try:
            response = await client.request(method, path, **kwargs)

            log_with_source(
                logger,
                "cli",
                "debug",
                "API response",
                method=method,
                path=path,
                status_code=response.status_code,
            )

            return response

        except httpx.HTTPError as e:
            log_with_source(
                logger,
                "cli",
                "error",
                "API request failed",
                method=method,
                path=path,
                error=str(e),
            )
            raise

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a GET request."""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a POST request."""
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a PUT request."""
        return await self.request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a PATCH request."""
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a DELETE request."""
        return await self.request("DELETE", path, **kwargs)


# Module-level client instance
_client: APIClient | None = None


def get_api_client() -> APIClient:
    """Get or create the API client singleton."""
    global _client
    if _client is None:
        _client = APIClient()
    return _client


async def close_api_client() -> None:
    """Close the API client."""
    global _client
    if _client:
        await _client.close()
        _client = None
