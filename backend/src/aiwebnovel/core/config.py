"""Typed application configuration sourced from environment variables."""

import os
import re
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_COOKIE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_HTTP_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")
_MAX_TRUSTED_HOSTS = 16


def normalize_data_root(value: str | os.PathLike[str]) -> Path:
    """Return one absolute, lexical data root without touching the filesystem."""
    raw_value = os.fspath(value)
    if "\x00" in raw_value:
        raise ValueError("data_root must not contain null bytes")

    normalized_text = raw_value.strip()
    if not normalized_text:
        raise ValueError("data_root must not be blank")

    candidate = Path(normalized_text)
    if not candidate.is_absolute():
        raise ValueError("data_root must be an absolute path")

    normalized = Path(os.path.normpath(normalized_text))
    anchor = normalized.anchor
    if not anchor or normalized == Path(anchor):
        raise ValueError("data_root must not be a filesystem root")
    return normalized


def _default_data_root() -> Path:
    """Derive the Windows default without falling back to another location."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data is None or not local_app_data.strip():
        raise ValueError("LOCALAPPDATA is required when data_root is not configured")
    return normalize_data_root(Path(local_app_data) / "AIWebNovel")


class Settings(BaseSettings):
    """Validated settings for the local backend process."""

    model_config = SettingsConfigDict(
        env_prefix="AIWEBNOVEL_",
        env_file=None,
        case_sensitive=False,
        extra="ignore",
        frozen=True,
        validate_default=True,
    )

    app_name: str = "AIWebNovel"
    app_version: str = "0.0.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    host: Literal["127.0.0.1", "::1"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    data_root: Path = Field(default_factory=_default_data_root)
    database_url: str | None = None
    database_echo: bool = False
    database_busy_timeout_ms: int = Field(default=5000, ge=1, le=600_000)
    serve_frontend: bool = False
    frontend_dist_path: Path = Path("frontend/dist")
    cors_allowed_origins: tuple[str, ...] = ("http://127.0.0.1:5173",)
    trusted_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")
    max_request_body_bytes: int = Field(default=1_048_576, ge=1, le=16_777_216)
    session_cookie_name: str = "aiwebnovel_session"
    session_ttl_seconds: int = Field(default=28_800, ge=60, le=604_800)
    session_max_entries: int = Field(default=16, ge=1, le=256)
    csrf_header_name: str = "X-CSRF-Token"
    expose_api_docs: bool = True

    @field_validator("app_name", "app_version")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        """Reject blank identifying configuration values."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        """Normalize the deployment mode used by security defaults."""
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("environment must not be blank")
        return normalized

    @field_validator("data_root", mode="before")
    @classmethod
    def validate_data_root(cls, value: object) -> Path:
        """Validate and normalize the managed root without creating it."""
        if not isinstance(value, (str, os.PathLike)):
            raise ValueError("data_root must be a filesystem path")
        return normalize_data_root(value)

    @field_validator("database_url")
    @classmethod
    def validate_database_url_text(cls, value: str | None) -> str | None:
        """Keep an explicit database URL optional while rejecting blank overrides."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("database_url must not be blank")
        return normalized

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        """Require an absolute API prefix without a trailing slash."""
        normalized = value.strip()
        if normalized != "/api" and not normalized.startswith("/api/"):
            raise ValueError("api_prefix must remain within the reserved /api namespace")
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
    def validate_cors_allowed_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
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
                _validated_port = parsed.port
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
                raise ValueError("CORS origins must contain only scheme, host, and optional port")
            if normalized in normalized_origins:
                raise ValueError("CORS origins must not contain duplicates")
            normalized_origins.append(normalized)

        return tuple(normalized_origins)

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts(cls, hosts: tuple[str, ...]) -> tuple[str, ...]:
        """Accept a small exact host allowlist without ports or URL components."""
        if not hosts or len(hosts) > _MAX_TRUSTED_HOSTS:
            raise ValueError("trusted_hosts must contain between 1 and 16 entries")

        normalized_hosts: list[str] = []
        for host in hosts:
            normalized = host.strip().lower()
            if (
                not normalized
                or normalized == "*"
                or any(character.isspace() or ord(character) < 32 for character in normalized)
                or any(character in normalized for character in "/?#@[]")
            ):
                raise ValueError("trusted_hosts entries must be exact hosts without URL syntax")

            try:
                parsed_ip = ip_address(normalized)
            except ValueError:
                if ":" in normalized or len(normalized) > 253:
                    raise ValueError(
                        "trusted_hosts entries must be valid hostnames or IPs"
                    ) from None
                labels = normalized.split(".")
                if any(not _HOST_LABEL.fullmatch(label) for label in labels):
                    raise ValueError(
                        "trusted_hosts entries must be valid hostnames or IPs"
                    ) from None
                canonical = normalized
            else:
                canonical = parsed_ip.compressed

            if canonical in normalized_hosts:
                raise ValueError("trusted_hosts entries must not contain duplicates")
            normalized_hosts.append(canonical)

        return tuple(normalized_hosts)

    @field_validator("session_cookie_name")
    @classmethod
    def validate_session_cookie_name(cls, value: str) -> str:
        """Keep the local-session cookie name within one conservative token subset."""
        normalized = value.strip()
        if _COOKIE_NAME.fullmatch(normalized) is None:
            raise ValueError("session_cookie_name contains unsafe characters")
        return normalized

    @field_validator("csrf_header_name")
    @classmethod
    def validate_csrf_header_name(cls, value: str) -> str:
        """Require one valid HTTP field name for CSRF proof."""
        normalized = value.strip()
        if _HTTP_HEADER_NAME.fullmatch(normalized) is None:
            raise ValueError("csrf_header_name contains unsafe characters")
        return normalized

    @model_validator(mode="after")
    def apply_environment_security_defaults(self) -> "Settings":
        """Disable API documentation by default outside development and tests."""
        if "expose_api_docs" not in self.model_fields_set:
            object.__setattr__(
                self,
                "expose_api_docs",
                self.environment in {"development", "test"},
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings, cached until explicitly cleared."""
    return Settings()
