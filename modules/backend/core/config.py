"""
Configuration Management.

Loads secrets from config/.env and settings from config/settings/*.yaml.
No hardcoded values in code — all configuration comes from these sources.

Secrets (.env):
    DB_PASSWORD, REDIS_PASSWORD, JWT_SECRET, API_KEY_SALT,
    TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET

Settings (YAML):
    application.yaml - App identity, server, cors, telegram, pagination
    database.yaml    - Database and Redis connection settings
    logging.yaml     - Logging configuration
    features.yaml    - Feature flags
    security.yaml    - JWT settings
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root() -> Path:
    """Find project root by looking for .project_root marker file."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".project_root").exists():
            return current
        current = current.parent
    raise RuntimeError("Project root not found. Ensure .project_root file exists.")


def load_yaml_config(filename: str) -> dict[str, Any]:
    """Load a YAML configuration file from config/settings/."""
    project_root = find_project_root()
    config_path = project_root / "config" / "settings" / filename

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    """Secrets loaded from config/.env. Only passwords, tokens, and keys."""

    db_password: str
    redis_password: str
    jwt_secret: str
    api_key_salt: str
    telegram_bot_token: str
    telegram_webhook_secret: str

    model_config = SettingsConfigDict(
        env_file="config/.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class AppConfig:
    """Application configuration loaded from YAML files."""

    def __init__(self) -> None:
        self._application = load_yaml_config("application.yaml")
        self._database = load_yaml_config("database.yaml")
        self._logging = load_yaml_config("logging.yaml")
        self._features = load_yaml_config("features.yaml")
        self._security = load_yaml_config("security.yaml")

    @property
    def application(self) -> dict[str, Any]:
        """Application settings."""
        return self._application

    @property
    def database(self) -> dict[str, Any]:
        """Database settings."""
        return self._database

    @property
    def logging(self) -> dict[str, Any]:
        """Logging settings."""
        return self._logging

    @property
    def features(self) -> dict[str, Any]:
        """Feature flags."""
        return self._features

    @property
    def security(self) -> dict[str, Any]:
        """Security settings."""
        return self._security


@lru_cache
def get_settings() -> Settings:
    """Get cached secrets instance."""
    return Settings()


@lru_cache
def get_app_config() -> AppConfig:
    """Get cached application configuration."""
    return AppConfig()


def get_database_url(async_driver: bool = True) -> str:
    """
    Construct database URL from YAML config and secrets.

    Args:
        async_driver: Use asyncpg driver if True, psycopg2 if False.

    Returns:
        Database connection URL string.
    """
    db = get_app_config().database
    password = get_settings().db_password
    driver = "postgresql+asyncpg" if async_driver else "postgresql"
    return f"{driver}://{db['user']}:{password}@{db['host']}:{db['port']}/{db['name']}"


def get_redis_url() -> str:
    """
    Construct Redis URL from YAML config and secrets.

    Returns:
        Redis connection URL string.
    """
    redis = get_app_config().database["redis"]
    password = get_settings().redis_password
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{redis['host']}:{redis['port']}/{redis['db']}"
