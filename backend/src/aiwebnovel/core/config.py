"""Typed application configuration sourced from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

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
    serve_frontend: bool = False
    frontend_dist_path: Path = Path("frontend/dist")
    cors_allowed_origins: tuple[str, ...] = ("http://127.0.0.1:5173",)

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

    @field_validator("frontend_dist_path", mode="before")
    @classmethod
    def validate_frontend_dist_path(cls, value: object) -> object:
        """Reject blank build paths without touching the filesystem."""
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("frontend_dist_path must not be blank")
            return Path(normalized)
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_allowed_origins(
        cls, origins: tuple[str, ...]
    ) -> tuple[str, ...]:
        """Require explicit HTTP origins without paths, wildcards, or credentials."""
        normalized_origins: list[str] = []
        for origin in origins:
            normalized = origin.strip()
            if (
                not normalized
                or "*" in normalized
                or "?" in normalized
                or "#" in normalized
                or any(character.isspace() for character in normalized)
            ):
                raise ValueError("CORS origins must be explicit")

            parsed = urlsplit(normalized)
            try:
                parsed_port = parsed.port
            except ValueError as exc:
                raise ValueError("CORS origin has an invalid port") from exc

            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname is None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError(
                    "CORS origins must contain only scheme, host, and optional port"
                )
            if normalized in normalized_origins:
                raise ValueError("CORS origins must not contain duplicates")
            normalized_origins.append(normalized)

        return tuple(normalized_origins)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings, cached until explicitly cleared."""
    return Settings()
