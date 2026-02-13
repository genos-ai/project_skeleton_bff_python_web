"""
Unit Tests for Health Check Endpoints.

Tests the health check functionality including:
- Liveness check (/health)
- Readiness check (/health/ready)
- Detailed health check (/health/detailed)
- Database and Redis connectivity checks
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestHealthCheck:
    """Tests for the liveness health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_healthy(self):
        """Should return healthy status."""
        from modules.backend.api.health import health_check

        result = await health_check()

        assert result == {"status": "healthy"}


class TestCheckDatabase:
    """Tests for the database health check function."""

    @pytest.mark.asyncio
    async def test_returns_not_configured_when_no_db_host(self):
        """Should return not_configured when database host is not set."""
        from modules.backend.api.health import check_database

        mock_settings = MagicMock()
        mock_settings.db_host = None
        mock_settings.db_name = "test"

        with patch(
            "modules.backend.core.config.get_settings",
            return_value=mock_settings,
        ):
            result = await check_database()

        assert result == {"status": "not_configured"}

    @pytest.mark.asyncio
    async def test_returns_not_configured_when_no_db_name(self):
        """Should return not_configured when database name is not set."""
        from modules.backend.api.health import check_database

        mock_settings = MagicMock()
        mock_settings.db_host = "localhost"
        mock_settings.db_name = None

        with patch(
            "modules.backend.core.config.get_settings",
            return_value=mock_settings,
        ):
            result = await check_database()

        assert result == {"status": "not_configured"}

    @pytest.mark.asyncio
    async def test_returns_healthy_on_successful_connection(self):
        """Should return healthy with latency when database is reachable."""
        from modules.backend.api.health import check_database

        mock_settings = MagicMock()
        mock_settings.db_host = "localhost"
        mock_settings.db_name = "test"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        async def mock_get_db_session():
            yield mock_session

        with patch(
            "modules.backend.core.config.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "modules.backend.core.database.get_db_session",
                mock_get_db_session,
            ):
                result = await check_database()

        assert result["status"] == "healthy"
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], int)

    @pytest.mark.asyncio
    async def test_returns_unhealthy_on_connection_error(self):
        """Should return unhealthy with error message when database is unreachable."""
        from modules.backend.api.health import check_database

        mock_settings = MagicMock()
        mock_settings.db_host = "localhost"
        mock_settings.db_name = "test"

        async def mock_get_db_session_error():
            raise Exception("Connection refused")
            yield  # Make it a generator

        with patch(
            "modules.backend.core.config.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "modules.backend.core.database.get_db_session",
                mock_get_db_session_error,
            ):
                result = await check_database()

        assert result["status"] == "unhealthy"
        assert "error" in result
        assert "Connection refused" in result["error"]


class TestCheckRedis:
    """Tests for the Redis health check function."""

    @pytest.mark.asyncio
    async def test_returns_not_configured_when_no_redis_url(self):
        """Should return not_configured when Redis URL is not set."""
        from modules.backend.api.health import check_redis

        mock_settings = MagicMock()
        mock_settings.redis_url = None

        with patch(
            "modules.backend.core.config.get_settings",
            return_value=mock_settings,
        ):
            result = await check_redis()

        assert result == {"status": "not_configured"}

    @pytest.mark.asyncio
    async def test_returns_healthy_on_successful_ping(self):
        """Should return healthy with latency when Redis is reachable."""
        from modules.backend.api.health import check_redis

        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379"

        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.aclose = AsyncMock()

        with patch(
            "modules.backend.core.config.get_settings",
            return_value=mock_settings,
        ):
            with patch("redis.asyncio.from_url", return_value=mock_client):
                result = await check_redis()

        assert result["status"] == "healthy"
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], int)
        mock_client.ping.assert_called_once()
        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_unhealthy_on_connection_error(self):
        """Should return unhealthy with error message when Redis is unreachable."""
        from modules.backend.api.health import check_redis

        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379"

        with patch(
            "modules.backend.core.config.get_settings",
            return_value=mock_settings,
        ):
            with patch(
                "redis.asyncio.from_url",
                side_effect=Exception("Connection refused"),
            ):
                result = await check_redis()

        assert result["status"] == "unhealthy"
        assert "error" in result
        assert "Connection refused" in result["error"]


class TestReadinessCheck:
    """Tests for the readiness health check endpoint."""

    @pytest.mark.asyncio
    async def test_returns_healthy_when_all_checks_pass(self):
        """Should return healthy when all dependency checks pass."""
        from modules.backend.api.health import readiness_check

        with patch(
            "modules.backend.api.health.check_database",
            return_value={"status": "healthy", "latency_ms": 5},
        ):
            with patch(
                "modules.backend.api.health.check_redis",
                return_value={"status": "healthy", "latency_ms": 1},
            ):
                result = await readiness_check()

        assert result["status"] == "healthy"
        assert result["checks"]["database"]["status"] == "healthy"
        assert result["checks"]["redis"]["status"] == "healthy"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_returns_healthy_when_dependencies_not_configured(self):
        """Should return healthy when dependencies are not configured."""
        from modules.backend.api.health import readiness_check

        with patch(
            "modules.backend.api.health.check_database",
            return_value={"status": "not_configured"},
        ):
            with patch(
                "modules.backend.api.health.check_redis",
                return_value={"status": "not_configured"},
            ):
                result = await readiness_check()

        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_raises_503_when_database_unhealthy(self):
        """Should raise HTTPException 503 when database is unhealthy."""
        from fastapi import HTTPException
        from modules.backend.api.health import readiness_check

        with patch(
            "modules.backend.api.health.check_database",
            return_value={"status": "unhealthy", "error": "Connection refused"},
        ):
            with patch(
                "modules.backend.api.health.check_redis",
                return_value={"status": "healthy", "latency_ms": 1},
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await readiness_check()

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_raises_503_when_redis_unhealthy(self):
        """Should raise HTTPException 503 when Redis is unhealthy."""
        from fastapi import HTTPException
        from modules.backend.api.health import readiness_check

        with patch(
            "modules.backend.api.health.check_database",
            return_value={"status": "healthy", "latency_ms": 5},
        ):
            with patch(
                "modules.backend.api.health.check_redis",
                return_value={"status": "unhealthy", "error": "Connection refused"},
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await readiness_check()

        assert exc_info.value.status_code == 503


class TestDetailedHealthCheck:
    """Tests for the detailed health check endpoint."""

    @pytest.mark.asyncio
    async def test_returns_comprehensive_status(self):
        """Should return comprehensive status including application info."""
        from modules.backend.api.health import detailed_health_check

        mock_settings = MagicMock()
        mock_settings.app_name = "test-app"
        mock_settings.app_env = "test"
        mock_settings.app_debug = False

        mock_app_config = MagicMock()
        mock_app_config.application = {"version": "1.0.0"}

        with patch(
            "modules.backend.api.health.check_database",
            return_value={"status": "healthy", "latency_ms": 5},
        ):
            with patch(
                "modules.backend.api.health.check_redis",
                return_value={"status": "healthy", "latency_ms": 1},
            ):
                with patch(
                    "modules.backend.core.config.get_settings",
                    return_value=mock_settings,
                ):
                    with patch(
                        "modules.backend.core.config.get_app_config",
                        return_value=mock_app_config,
                    ):
                        result = await detailed_health_check()

        assert result["status"] == "healthy"
        assert result["application"]["name"] == "test-app"
        assert result["application"]["env"] == "test"
        assert result["application"]["version"] == "1.0.0"
        assert "checks" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_returns_unhealthy_when_check_fails(self):
        """Should return unhealthy overall status when any check fails."""
        from modules.backend.api.health import detailed_health_check

        mock_settings = MagicMock()
        mock_settings.app_name = "test-app"
        mock_settings.app_env = "test"
        mock_settings.app_debug = False

        mock_app_config = MagicMock()
        mock_app_config.application = {"version": "1.0.0"}

        with patch(
            "modules.backend.api.health.check_database",
            return_value={"status": "unhealthy", "error": "Connection refused"},
        ):
            with patch(
                "modules.backend.api.health.check_redis",
                return_value={"status": "healthy", "latency_ms": 1},
            ):
                with patch(
                    "modules.backend.core.config.get_settings",
                    return_value=mock_settings,
                ):
                    with patch(
                        "modules.backend.core.config.get_app_config",
                        return_value=mock_app_config,
                    ):
                        result = await detailed_health_check()

        assert result["status"] == "unhealthy"
