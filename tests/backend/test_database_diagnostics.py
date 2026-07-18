"""Tests for the public database diagnostic contract."""

from pathlib import Path

import pytest

import aiwebnovel.db.diagnostics as database_diagnostics
from aiwebnovel.core.config import Settings
from aiwebnovel.db import run_database_diagnostic
from aiwebnovel.storage.paths import StoragePaths

pytestmark = pytest.mark.unit


class _DisposableEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def test_public_database_diagnostic_runs_health_check_and_disposes_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(data_root=tmp_path / "diagnostic-root")
    paths = StoragePaths.from_settings(settings)
    engine = _DisposableEngine()
    observed: dict[str, object] = {}

    def create_engine(
        received_settings: Settings,
        *,
        storage_paths: StoragePaths,
    ) -> _DisposableEngine:
        observed["settings"] = received_settings
        observed["paths"] = storage_paths
        return engine

    def check_health(received_engine: object) -> None:
        observed["engine"] = received_engine

    monkeypatch.setattr(database_diagnostics, "create_database_engine", create_engine)
    monkeypatch.setattr(database_diagnostics, "check_database_health", check_health)

    run_database_diagnostic(settings, paths)

    assert observed == {"settings": settings, "paths": paths, "engine": engine}
    assert engine.disposed is True


def test_public_database_diagnostic_disposes_engine_after_health_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(data_root=tmp_path / "diagnostic-root")
    paths = StoragePaths.from_settings(settings)
    engine = _DisposableEngine()

    monkeypatch.setattr(
        database_diagnostics,
        "create_database_engine",
        lambda _settings, *, storage_paths: engine,
    )

    def fail_health_check(_engine: object) -> None:
        raise RuntimeError("database diagnostic failed")

    monkeypatch.setattr(database_diagnostics, "check_database_health", fail_health_check)

    with pytest.raises(RuntimeError, match="database diagnostic failed"):
        run_database_diagnostic(settings, paths)

    assert engine.disposed is True
