"""Database setting defaults, overrides, validation, and URL policy tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from aiwebnovel.core.config import Settings, get_settings
from aiwebnovel.db.engine import (
    DatabaseConfigurationError,
    create_database_engine,
    resolve_database_url,
)
from aiwebnovel.storage.paths import StoragePaths

pytestmark = pytest.mark.unit


_DATABASE_ENV_VARS = (
    "AIWEBNOVEL_DATABASE_URL",
    "AIWEBNOVEL_DATABASE_ECHO",
    "AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS",
)


@pytest.fixture(autouse=True)
def isolated_database_settings(monkeypatch: pytest.MonkeyPatch):
    for variable in _DATABASE_ENV_VARS:
        monkeypatch.delenv(variable, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_database_default_is_derived_from_the_managed_data_root() -> None:
    settings = get_settings()
    paths = StoragePaths.from_settings(settings)
    resolved_url = resolve_database_url(settings, paths)

    assert settings.database_url is None
    assert resolved_url.drivername == "sqlite+pysqlite"
    assert resolved_url.database == paths.database_file.as_posix()
    assert ".runtime" not in resolved_url.database
    assert settings.database_echo is False
    assert settings.database_busy_timeout_ms == 5000


def test_database_environment_overrides_are_typed_and_cacheable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIWEBNOVEL_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("AIWEBNOVEL_DATABASE_ECHO", "true")
    monkeypatch.setenv("AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS", "2345")

    first = get_settings()
    assert first.database_url == "sqlite+pysqlite:///:memory:"
    assert first.database_echo is True
    assert first.database_busy_timeout_ms == 2345

    monkeypatch.setenv("AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS", "3456")
    assert get_settings() is first
    assert get_settings().database_busy_timeout_ms == 2345

    get_settings.cache_clear()
    assert get_settings().database_busy_timeout_ms == 3456


def test_explicit_database_url_has_priority_over_storage_derivation(
    tmp_path: Path,
) -> None:
    explicit_url = "sqlite+pysqlite:///:memory:"
    settings = Settings(
        data_root=tmp_path / "managed root",
        database_url=explicit_url,
    )

    resolved = resolve_database_url(settings, StoragePaths.from_settings(settings))

    assert str(resolved) == explicit_url


@pytest.mark.parametrize("value", [0, -1, 600_001, "not-an-integer"])
def test_invalid_database_busy_timeout_is_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(database_busy_timeout_ms=value)


def test_invalid_database_echo_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_echo="not-a-boolean")


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://localhost/example",
        "mysql://localhost/example",
        "sqlite+aiosqlite:///:memory:",
    ],
)
def test_database_factory_rejects_unsupported_urls(database_url: str) -> None:
    with pytest.raises(DatabaseConfigurationError):
        create_database_engine(Settings(database_url=database_url))
