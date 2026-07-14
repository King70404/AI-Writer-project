"""Configuration defaults, validation, environment, and cache tests."""

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
    "AIWEBNOVEL_DATABASE_URL",
    "AIWEBNOVEL_DATABASE_ECHO",
    "AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS",
    "AIWEBNOVEL_SERVE_FRONTEND",
    "AIWEBNOVEL_FRONTEND_DIST_PATH",
    "AIWEBNOVEL_CORS_ALLOWED_ORIGINS",
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch):
    for variable in _SETTING_ENV_VARS:
        monkeypatch.delenv(variable, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_settings_are_local_and_versioned() -> None:
    settings = get_settings()

    assert settings.app_name == "AIWebNovel"
    assert settings.app_version == "0.0.0"
    assert settings.environment == "development"
    assert settings.api_prefix == "/api/v1"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.serve_frontend is False
    assert settings.frontend_dist_path.as_posix() == "frontend/dist"
    assert settings.cors_allowed_origins == ("http://127.0.0.1:5173",)


def test_environment_overrides_and_cache_can_be_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIWEBNOVEL_PORT", "8123")
    monkeypatch.setenv("AIWEBNOVEL_LOG_LEVEL", "debug")
    monkeypatch.setenv("AIWEBNOVEL_SERVE_FRONTEND", "true")
    monkeypatch.setenv("AIWEBNOVEL_FRONTEND_DIST_PATH", "local-build")
    monkeypatch.setenv(
        "AIWEBNOVEL_CORS_ALLOWED_ORIGINS",
        '["http://127.0.0.1:5174"]',
    )

    first = get_settings()
    assert first.port == 8123
    assert first.log_level == "DEBUG"
    assert first.serve_frontend is True
    assert first.frontend_dist_path.as_posix() == "local-build"
    assert first.cors_allowed_origins == ("http://127.0.0.1:5174",)

    monkeypatch.setenv("AIWEBNOVEL_PORT", "8124")
    assert get_settings() is first
    assert get_settings().port == 8123

    get_settings.cache_clear()
    assert get_settings().port == 8124


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
