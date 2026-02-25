"""
Unit Tests for Configuration Management.

Black box tests against the public interface of config.py.
Tests run against the real project files (YAML configs, .env).
Failure scenarios use tmp_path to create controlled filesystems.
No mocking — the config loader is the system under test.
"""

import pytest

from modules.backend.core.config import (
    AppConfig,
    Settings,
    find_project_root,
    get_app_config,
    get_database_url,
    get_redis_url,
    get_server_base_url,
    get_settings,
    load_yaml_config,
    validate_project_root,
)
from modules.backend.core.config_schema import (
    ApplicationSchema,
    DatabaseSchema,
    FeaturesSchema,
    GatewaySchema,
    LoggingSchema,
    SecuritySchema,
)


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """Clear lru_cache between tests so each test gets a fresh load."""
    get_settings.cache_clear()
    get_app_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_app_config.cache_clear()


# =============================================================================
# find_project_root
# =============================================================================


class TestFindProjectRoot:
    """Tests for .project_root marker discovery."""

    def test_finds_root_from_project_directory(self):
        root = find_project_root()
        assert root.is_dir()
        assert (root / ".project_root").exists()

    def test_config_directory_exists_at_root(self):
        root = find_project_root()
        assert (root / "config" / "settings").is_dir()
        assert (root / "config" / ".env").is_file()

    def test_raises_when_no_marker_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RuntimeError, match="Project root not found"):
            find_project_root()


class TestValidateProjectRoot:
    """Tests for the SystemExit wrapper around find_project_root."""

    def test_returns_path_when_marker_exists(self):
        root = validate_project_root()
        assert (root / ".project_root").exists()

    def test_exits_when_marker_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            validate_project_root()


# =============================================================================
# load_yaml_config
# =============================================================================


class TestLoadYamlConfig:
    """Tests for YAML file loading from config/settings/."""

    def test_loads_application_yaml_as_dict(self):
        data = load_yaml_config("application.yaml")
        assert isinstance(data, dict)
        assert "name" in data
        assert "server" in data

    def test_loads_database_yaml_as_dict(self):
        data = load_yaml_config("database.yaml")
        assert isinstance(data, dict)
        assert "host" in data
        assert "redis" in data

    def test_loads_all_config_files(self):
        """Every expected YAML file should be loadable."""
        filenames = [
            "application.yaml",
            "database.yaml",
            "logging.yaml",
            "features.yaml",
            "security.yaml",
            "gateway.yaml",
        ]
        for filename in filenames:
            data = load_yaml_config(filename)
            assert isinstance(data, dict), f"{filename} did not return a dict"
            assert len(data) > 0, f"{filename} returned empty dict"

    def test_raises_for_nonexistent_file(self):
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_yaml_config("does_not_exist.yaml")

    def test_returns_empty_dict_for_empty_yaml(self, tmp_path, monkeypatch):
        """An empty YAML file should return {} rather than None."""
        (tmp_path / ".project_root").touch()
        settings_dir = tmp_path / "config" / "settings"
        settings_dir.mkdir(parents=True)
        (settings_dir / "empty.yaml").write_text("")
        monkeypatch.chdir(tmp_path)

        result = load_yaml_config("empty.yaml")

        assert result == {}


# =============================================================================
# Settings (secrets from .env)
# =============================================================================


class TestSettings:
    """Tests for secret loading from config/.env."""

    def test_loads_from_env_file(self):
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_has_all_required_secret_fields(self):
        settings = get_settings()
        required = [
            "db_password",
            "redis_password",
            "jwt_secret",
            "api_key_salt",
            "telegram_bot_token",
            "telegram_webhook_secret",
            "anthropic_api_key",
        ]
        for field in required:
            assert hasattr(settings, field), f"Missing field: {field}"
            assert isinstance(getattr(settings, field), str)

    def test_secrets_are_nonempty_strings(self):
        """Critical secrets must not be blank (redis_password may be empty)."""
        settings = get_settings()
        assert len(settings.db_password) > 0
        assert len(settings.jwt_secret) > 0
        assert len(settings.api_key_salt) > 0


# =============================================================================
# AppConfig (validated YAML)
# =============================================================================


class TestAppConfig:
    """Tests for validated YAML configuration loading."""

    def test_loads_all_six_config_sections(self):
        config = AppConfig()
        assert config.application is not None
        assert config.database is not None
        assert config.logging is not None
        assert config.features is not None
        assert config.security is not None
        assert config.gateway is not None

    def test_application_returns_typed_schema(self):
        config = AppConfig()
        assert isinstance(config.application, ApplicationSchema)

    def test_database_returns_typed_schema(self):
        config = AppConfig()
        assert isinstance(config.database, DatabaseSchema)

    def test_logging_returns_typed_schema(self):
        config = AppConfig()
        assert isinstance(config.logging, LoggingSchema)

    def test_features_returns_typed_schema(self):
        config = AppConfig()
        assert isinstance(config.features, FeaturesSchema)

    def test_security_returns_typed_schema(self):
        config = AppConfig()
        assert isinstance(config.security, SecuritySchema)

    def test_gateway_returns_typed_schema(self):
        config = AppConfig()
        assert isinstance(config.gateway, GatewaySchema)

    def test_application_has_attribute_access(self):
        config = AppConfig()
        app = config.application
        assert isinstance(app.name, str)
        assert isinstance(app.version, str)
        assert isinstance(app.server.host, str)
        assert isinstance(app.server.port, int)

    def test_database_has_attribute_access(self):
        config = AppConfig()
        db = config.database
        assert isinstance(db.host, str)
        assert isinstance(db.port, int)
        assert isinstance(db.redis.host, str)
        assert isinstance(db.redis.port, int)

    def test_security_jwt_has_attribute_access(self):
        config = AppConfig()
        jwt = config.security.jwt
        assert isinstance(jwt.algorithm, str)
        assert isinstance(jwt.access_token_expire_minutes, int)
        assert isinstance(jwt.refresh_token_expire_days, int)

    def test_rejects_yaml_with_missing_required_fields(self, tmp_path, monkeypatch):
        """A YAML file missing required fields should fail Pydantic validation."""
        (tmp_path / ".project_root").touch()
        settings_dir = tmp_path / "config" / "settings"
        settings_dir.mkdir(parents=True)

        (settings_dir / "application.yaml").write_text("name: 'Incomplete'")
        (settings_dir / "database.yaml").write_text("host: localhost")
        (settings_dir / "logging.yaml").write_text("level: INFO")
        (settings_dir / "features.yaml").write_text("api_detailed_errors: true")
        (settings_dir / "security.yaml").write_text("jwt:\n  algorithm: HS256")
        (settings_dir / "gateway.yaml").write_text("default_policy: deny")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ValueError, match="Invalid configuration"):
            AppConfig()

    def test_rejects_yaml_with_unknown_fields(self):
        """extra='forbid' on schemas should reject unknown YAML keys."""
        from pydantic import ValidationError as PydanticValidationError

        data = load_yaml_config("application.yaml")
        data["unknown_field"] = "oops"
        with pytest.raises(PydanticValidationError, match="Extra inputs are not permitted"):
            ApplicationSchema(**data)


# =============================================================================
# Cached accessors
# =============================================================================


class TestGetSettings:
    """Tests for the cached get_settings() accessor."""

    def test_returns_settings_instance(self):
        assert isinstance(get_settings(), Settings)

    def test_caching_returns_same_instance(self):
        first = get_settings()
        second = get_settings()
        assert first is second


class TestGetAppConfig:
    """Tests for the cached get_app_config() accessor."""

    def test_returns_app_config_instance(self):
        assert isinstance(get_app_config(), AppConfig)

    def test_caching_returns_same_instance(self):
        first = get_app_config()
        second = get_app_config()
        assert first is second


# =============================================================================
# URL builders
# =============================================================================


class TestGetDatabaseUrl:
    """Tests for database URL construction."""

    def test_async_url_uses_asyncpg_driver(self):
        url = get_database_url(async_driver=True)
        assert url.startswith("postgresql+asyncpg://")

    def test_sync_url_uses_postgresql_driver(self):
        url = get_database_url(async_driver=False)
        assert url.startswith("postgresql://")
        assert "+asyncpg" not in url

    def test_url_contains_config_values(self):
        url = get_database_url()
        db = get_app_config().database
        assert f"@{db.host}:{db.port}/{db.name}" in url
        assert f"{db.user}:" in url

    def test_url_contains_password_from_secrets(self):
        url = get_database_url()
        password = get_settings().db_password
        assert f":{password}@" in url


class TestGetRedisUrl:
    """Tests for Redis URL construction."""

    def test_url_starts_with_redis_scheme(self):
        url = get_redis_url()
        assert url.startswith("redis://")

    def test_url_contains_config_values(self):
        url = get_redis_url()
        redis = get_app_config().database.redis
        assert f"{redis.host}:{redis.port}/{redis.db}" in url


class TestGetServerBaseUrl:
    """Tests for server base URL construction."""

    def test_returns_url_and_timeout_tuple(self):
        result = get_server_base_url()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_url_is_http_format(self):
        base_url, _ = get_server_base_url()
        assert base_url.startswith("http://")

    def test_url_contains_host_and_port(self):
        base_url, _ = get_server_base_url()
        server = get_app_config().application.server
        assert f"{server.host}:{server.port}" in base_url

    def test_timeout_is_positive_float(self):
        _, timeout = get_server_base_url()
        assert isinstance(timeout, float)
        assert timeout > 0
