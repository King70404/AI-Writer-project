"""Configuration defaults, storage paths, environment, and cache tests."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from aiwebnovel.core.config import (
    Settings,
    get_settings,
    resolve_default_data_root,
    resolve_local_app_data_root,
)

pytestmark = pytest.mark.unit


_SETTING_ENV_VARS = (
    "AIWEBNOVEL_APP_NAME",
    "AIWEBNOVEL_APP_VERSION",
    "AIWEBNOVEL_ENVIRONMENT",
    "AIWEBNOVEL_API_PREFIX",
    "AIWEBNOVEL_HOST",
    "AIWEBNOVEL_PORT",
    "AIWEBNOVEL_LOG_LEVEL",
    "AIWEBNOVEL_DATA_ROOT",
    "AIWEBNOVEL_DATABASE_URL",
    "AIWEBNOVEL_DATABASE_ECHO",
    "AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS",
    "AIWEBNOVEL_SERVE_FRONTEND",
    "AIWEBNOVEL_FRONTEND_DIST_PATH",
    "AIWEBNOVEL_CORS_ALLOWED_ORIGINS",
    "AIWEBNOVEL_TRUSTED_HOSTS",
    "AIWEBNOVEL_MAX_REQUEST_BODY_BYTES",
    "AIWEBNOVEL_SESSION_COOKIE_NAME",
    "AIWEBNOVEL_SESSION_TTL_SECONDS",
    "AIWEBNOVEL_SESSION_MAX_ENTRIES",
    "AIWEBNOVEL_CSRF_HEADER_NAME",
    "AIWEBNOVEL_EXPOSE_API_DOCS",
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    for variable in _SETTING_ENV_VARS:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv(
        "AIWEBNOVEL_DATA_ROOT",
        os.fspath(tmp_path / "isolated-config-data-root"),
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_settings_are_local_and_versioned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_app_data = tmp_path / "Local App Data"
    monkeypatch.delenv("AIWEBNOVEL_DATA_ROOT")
    monkeypatch.setenv("LOCALAPPDATA", os.fspath(local_app_data))
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_name == "AIWebNovel"
    assert settings.app_version == "0.0.0"
    assert settings.environment == "development"
    assert settings.api_prefix == "/api/v1"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.data_root == local_app_data / "AIWebNovel"
    assert settings.serve_frontend is False
    assert settings.frontend_dist_path.as_posix() == "frontend/dist"
    assert settings.cors_allowed_origins == ("http://127.0.0.1:5173",)
    assert settings.trusted_hosts == ("127.0.0.1", "localhost")
    assert settings.max_request_body_bytes == 1_048_576
    assert settings.session_cookie_name == "aiwebnovel_session"
    assert settings.session_ttl_seconds == 28_800
    assert settings.session_max_entries == 16
    assert settings.csrf_header_name == "X-CSRF-Token"
    assert settings.expose_api_docs is True
    assert not local_app_data.exists()


def test_local_app_data_boundary_is_public_and_read_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_app_data = tmp_path / "Local App Data"
    monkeypatch.setenv("LOCALAPPDATA", os.fspath(local_app_data))

    resolved = resolve_local_app_data_root()

    assert resolved == local_app_data
    assert not local_app_data.exists()

    formal_root = resolve_default_data_root()

    assert formal_root == local_app_data / "AIWebNovel"
    assert not formal_root.exists()


def test_environment_overrides_and_cache_can_be_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIWEBNOVEL_PORT", "8123")
    monkeypatch.setenv("AIWEBNOVEL_LOG_LEVEL", "debug")
    monkeypatch.setenv("AIWEBNOVEL_SERVE_FRONTEND", "true")
    data_root = Path(os.environ["AIWEBNOVEL_DATA_ROOT"])
    monkeypatch.setenv("AIWEBNOVEL_FRONTEND_DIST_PATH", "local-build")
    monkeypatch.setenv(
        "AIWEBNOVEL_CORS_ALLOWED_ORIGINS",
        '["http://127.0.0.1:5174"]',
    )
    monkeypatch.setenv(
        "AIWEBNOVEL_TRUSTED_HOSTS",
        '["127.0.0.1","localhost"]',
    )
    monkeypatch.setenv("AIWEBNOVEL_MAX_REQUEST_BODY_BYTES", "2048")
    monkeypatch.setenv("AIWEBNOVEL_SESSION_COOKIE_NAME", "local_session")
    monkeypatch.setenv("AIWEBNOVEL_SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("AIWEBNOVEL_SESSION_MAX_ENTRIES", "8")
    monkeypatch.setenv("AIWEBNOVEL_CSRF_HEADER_NAME", "X-Local-CSRF")
    monkeypatch.setenv("AIWEBNOVEL_EXPOSE_API_DOCS", "false")

    first = get_settings()
    assert first.port == 8123
    assert first.log_level == "DEBUG"
    assert first.serve_frontend is True
    assert first.data_root == data_root
    assert first.frontend_dist_path.as_posix() == "local-build"
    assert first.cors_allowed_origins == ("http://127.0.0.1:5174",)
    assert first.trusted_hosts == ("127.0.0.1", "localhost")
    assert first.max_request_body_bytes == 2048
    assert first.session_cookie_name == "local_session"
    assert first.session_ttl_seconds == 3600
    assert first.session_max_entries == 8
    assert first.csrf_header_name == "X-Local-CSRF"
    assert first.expose_api_docs is False

    monkeypatch.setenv("AIWEBNOVEL_PORT", "8124")
    assert get_settings() is first
    assert get_settings().port == 8123

    get_settings.cache_clear()
    assert get_settings().port == 8124


def test_explicit_data_root_does_not_require_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    explicit_root = tmp_path / "explicit data root"
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("AIWEBNOVEL_DATA_ROOT", os.fspath(explicit_root))
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.data_root == explicit_root
    assert not explicit_root.exists()


@pytest.mark.parametrize("local_value", [None, "", "   "])
def test_missing_or_empty_local_app_data_fails_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
    local_value: str | None,
) -> None:
    monkeypatch.delenv("AIWEBNOVEL_DATA_ROOT", raising=False)
    if local_value is None:
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
    else:
        monkeypatch.setenv("LOCALAPPDATA", local_value)
    get_settings.cache_clear()

    with pytest.raises((ValidationError, ValueError)):
        get_settings()


@pytest.mark.parametrize("local_value", ["relative-local-app-data", "C:drive-relative"])
def test_invalid_local_app_data_fails_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
    local_value: str,
) -> None:
    monkeypatch.delenv("AIWEBNOVEL_DATA_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", local_value)
    get_settings.cache_clear()

    with pytest.raises((ValidationError, ValueError)):
        get_settings()


@pytest.mark.parametrize(
    "data_root",
    ["relative/data", "", "   ", "\x00invalid"],
)
def test_invalid_data_roots_are_rejected(data_root: str) -> None:
    with pytest.raises((ValidationError, ValueError)):
        Settings(data_root=data_root)


def test_filesystem_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises((ValidationError, ValueError)):
        Settings(data_root=Path(tmp_path.anchor))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("port", 0),
        ("port", 65536),
        ("api_prefix", "api/v1"),
        ("api_prefix", "/custom/v1"),
        ("api_prefix", "/api/v1/"),
        ("host", "0.0.0.0"),
        ("host", "192.168.1.20"),
        ("log_level", "VERBOSE"),
        ("environment", "   "),
        ("serve_frontend", "maybe"),
        ("frontend_dist_path", "   "),
        ("cors_allowed_origins", ("*",)),
        ("cors_allowed_origins", ("http://*.example.invalid:5173",)),
        ("cors_allowed_origins", ("http://127.0.0.1:5173/path",)),
        ("cors_allowed_origins", ("http://127.0.0.1:5173?query=yes",)),
        ("cors_allowed_origins", ("http://127.0.0.1:5173#fragment",)),
        ("cors_allowed_origins", ("http://user@127.0.0.1:5173",)),
        (
            "cors_allowed_origins",
            ("http://127.0.0.1:5173", "http://127.0.0.1:5173"),
        ),
        ("trusted_hosts", ()),
        ("trusted_hosts", ("*",)),
        ("trusted_hosts", ("localhost:8000",)),
        ("trusted_hosts", ("http://localhost",)),
        ("trusted_hosts", ("user@localhost",)),
        ("trusted_hosts", ("localhost/path",)),
        ("trusted_hosts", ("localhost?query=yes",)),
        ("max_request_body_bytes", 0),
        ("max_request_body_bytes", 16_777_217),
        ("session_ttl_seconds", 59),
        ("session_ttl_seconds", 604_801),
        ("session_max_entries", 0),
        ("session_max_entries", 257),
        ("session_cookie_name", "unsafe cookie"),
        ("csrf_header_name", "Unsafe Header"),
    ],
)
def test_invalid_configuration_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_api_document_exposure_defaults_follow_environment_without_side_effects(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "configuration-only-root"

    development = Settings(environment="development", data_root=data_root)
    test = Settings(environment="test", data_root=data_root)
    production = Settings(environment="production", data_root=data_root)
    explicitly_enabled = Settings(
        environment="production",
        expose_api_docs=True,
        data_root=data_root,
    )

    assert development.expose_api_docs is True
    assert test.expose_api_docs is True
    assert production.expose_api_docs is False
    assert explicitly_enabled.expose_api_docs is True
    assert not data_root.exists()
