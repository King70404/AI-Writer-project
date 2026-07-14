"""Typed application configuration sourced from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated settings for the local backend process."""

    model_config = SettingsConfigDict(
        env_prefix="AIWEBNOVEL_",
        env_file=None,
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    app_name: str = "AIWebNovel"
    app_version: str = "0.0.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    database_url: str = "sqlite+pysqlite:///./.runtime/aiwebnovel-dev.sqlite3"
    database_echo: bool = False
    database_busy_timeout_ms: int = Field(default=5000, ge=1, le=600_000)

    @field_validator("app_name", "app_version", "environment", "database_url")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        """Reject blank identifying configuration values."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        """Require an absolute API prefix without a trailing slash."""
        normalized = value.strip()
        if not normalized.startswith("/"):
            raise ValueError("api_prefix must start with '/'")
        if normalized == "/" or normalized.endswith("/"):
            raise ValueError("api_prefix must identify a non-root path without a trailing slash")
        return normalized

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        """Accept case-insensitive string log levels before validation."""
        if isinstance(value, str):
            return value.strip().upper()
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings, cached until explicitly cleared."""
    return Settings()
