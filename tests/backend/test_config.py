"""Configuration defaults, validation, environment, and cache tests."""

import pytest
from pydantic import ValidationError

from aiwebnovel.core.config import Settings, get_settings


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


def test_environment_overrides_and_cache_can_be_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIWEBNOVEL_PORT", "8123")
    monkeypatch.setenv("AIWEBNOVEL_LOG_LEVEL", "debug")

    first = get_settings()
    assert first.port == 8123
    assert first.log_level == "DEBUG"

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
    ],
)
def test_invalid_configuration_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})
