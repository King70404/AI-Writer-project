"""Configuration defaults, storage paths, environment, and cache tests."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from aiwebnovel.core.config import Settings, get_settings

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
    assert not local_app_data.exists()


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

    first = get_settings()
    assert first.port == 8123
    assert first.log_level == "DEBUG"
    assert first.serve_frontend is True
    assert first.data_root == data_root
    assert first.frontend_dist_path.as_posix() == "local-build"
    assert first.cors_allowed_origins == ("http://127.0.0.1:5174",)

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
        ("api_prefix", "/api/v1/"),
        ("host", "0.0.0.0"),
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
    ],
)
def test_invalid_configuration_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})
