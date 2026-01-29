"""
Configuration Management.

Loads settings from environment variables and YAML configuration files.
All configuration must come from these sources - no hardcoded values in code.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings


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
    """Application settings loaded from environment variables."""

    # Database
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str

    # Redis
    redis_url: str

    # Security
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    api_key_salt: str

    # Application
    app_name: str = "BFF Application"
    app_env: str = "development"
    app_debug: bool = False
    app_log_level: str = "INFO"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # CORS
    cors_origins: list[str] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v or []

    @property
    def database_url(self) -> str:
        """Construct async database URL."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def sync_database_url(self) -> str:
        """Construct sync database URL for Alembic."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = "config/.env"
        env_file_encoding = "utf-8"
        case_sensitive = False


class AppConfig:
    """Application configuration loaded from YAML files."""

    def __init__(self) -> None:
        self._application = load_yaml_config("application.yaml")
        self._database = load_yaml_config("database.yaml")
        self._logging = load_yaml_config("logging.yaml")
        self._features = load_yaml_config("features.yaml")

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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


@lru_cache
def get_app_config() -> AppConfig:
    """Get cached application configuration."""
    return AppConfig()
