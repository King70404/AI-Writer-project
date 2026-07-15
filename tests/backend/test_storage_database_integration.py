"""FastAPI storage lifecycle, database derivation, and failure isolation tests."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from aiwebnovel.core.config import Settings, get_settings
from aiwebnovel.core.middleware import is_valid_request_id
from aiwebnovel.db.engine import create_database_engine, resolve_database_url
from aiwebnovel.main import create_app
from aiwebnovel.storage.access import StorageAccessError
from aiwebnovel.storage.initializer import initialize_storage
from aiwebnovel.storage.paths import StoragePaths

from .factories import TestStorageIsolationError, create_test_app, create_test_settings

pytestmark = pytest.mark.integration


def _remove_root(root: Path, container: Path) -> None:
    if root.exists():
        assert root.is_relative_to(container)
        assert not root.is_symlink()
        shutil.rmtree(root)


def test_test_factory_refuses_an_implicit_or_relative_data_root(tmp_path: Path) -> None:
    with pytest.raises(TestStorageIsolationError):
        create_test_app(data_root=None)
    with pytest.raises(TestStorageIsolationError):
        create_test_app(data_root=Path("relative-test-root"))
    assert not (tmp_path / "unused").exists()


def test_default_database_is_created_only_after_storage_and_readiness(
    tmp_path: Path,
) -> None:
    root = tmp_path / "application data root"
    settings = create_test_settings(data_root=root)
    paths = StoragePaths.from_settings(settings)
    app = create_app(settings)

    assert not root.exists()
    try:
        with TestClient(app) as client:
            assert all(path.is_dir() for path in paths.directories)
            assert not paths.database_file.exists()
            response = client.get("/api/v1/health/ready")
            assert response.status_code == 200
            assert response.json() == {
                "status": "ready",
                "checks": {
                    "configuration": "ok",
                    "application": "ok",
                    "storage": "ok",
                    "database": "ok",
                    "frontend": "not_required",
                },
            }
            assert paths.database_file.is_file()
            assert app.state.database_engine.url.database == paths.database_file.as_posix()
            assert inspect(app.state.database_engine).get_table_names() == []
        assert app.state.database_engine is None
        assert app.state.database_session_factory is None
    finally:
        _remove_root(root, tmp_path)


def test_windows_path_with_spaces_round_trips_through_sqlalchemy_url(
    tmp_path: Path,
) -> None:
    root = tmp_path / "含 空格" / "managed data"
    root.parent.mkdir()
    settings = create_test_settings(data_root=root)
    paths = StoragePaths.from_settings(settings)
    initialize_storage(paths)
    resolved_url = resolve_database_url(settings, paths)

    assert resolved_url.database == paths.database_file.as_posix()
    engine = create_database_engine(settings, resolved_url, storage_paths=paths)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert paths.database_file.is_file()
    finally:
        engine.dispose()
        _remove_root(root, tmp_path)


def test_configuration_failure_keeps_live_available_and_ready_private(
    tmp_path: Path,
) -> None:
    private_marker = str(tmp_path / "private-configuration-path")

    def invalid_settings() -> Settings:
        raise ValueError(f"controlled invalid configuration {private_marker}")

    app = create_app(settings_provider=invalid_settings)

    with TestClient(app) as client:
        live = client.get("/api/v1/health/live")
        ready = client.get(
            "/api/v1/health/ready",
            headers={"X-Request-ID": "storage-config-failure"},
        )

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json() == {
        "status": "not_ready",
        "checks": {
            "configuration": "failed",
            "application": "ok",
            "storage": "failed",
            "database": "failed",
            "frontend": "not_required",
        },
    }
    assert ready.headers["X-Request-ID"] == "storage-config-failure"
    assert is_valid_request_id(ready.headers["X-Request-ID"])
    assert private_marker not in ready.text


def test_missing_local_app_data_does_not_fallback_or_disable_live(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("AIWEBNOVEL_DATA_ROOT", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        live = client.get("/api/v1/health/live")
        ready = client.get("/api/v1/health/ready")

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json()["checks"] == {
        "configuration": "failed",
        "application": "ok",
        "storage": "failed",
        "database": "failed",
        "frontend": "not_required",
    }
    assert not (tmp_path / "AIWebNovel").exists()
    get_settings.cache_clear()


def test_root_file_causes_storage_failure_without_database_creation(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root-is-a-file"
    root.write_text("preserve", encoding="utf-8")
    settings = create_test_settings(data_root=root)
    paths = StoragePaths.from_settings(settings)
    app = create_app(settings)

    try:
        caplog.set_level(logging.ERROR)
        with TestClient(app) as client:
            live = client.get("/api/v1/health/live")
            ready = client.get("/api/v1/health/ready")

        assert live.status_code == 200
        assert ready.status_code == 503
        assert ready.json()["checks"]["storage"] == "failed"
        assert ready.json()["checks"]["database"] == "failed"
        assert root.read_text(encoding="utf-8") == "preserve"
        assert not paths.database_file.exists()
        assert str(root) not in ready.text
        assert str(root) not in caplog.text
    finally:
        root.unlink(missing_ok=True)


def test_access_failure_stops_database_initialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "unwritable-storage"
    settings = create_test_settings(data_root=root)
    paths = StoragePaths.from_settings(settings)

    def denied_health(_paths: StoragePaths) -> None:
        raise StorageAccessError("controlled access failure")

    monkeypatch.setattr("aiwebnovel.main.check_storage_health", denied_health)
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            live = client.get("/api/v1/health/live")
            ready = client.get("/api/v1/health/ready")
        assert live.status_code == 200
        assert ready.status_code == 503
        assert ready.json()["checks"]["storage"] == "failed"
        assert ready.json()["checks"]["database"] == "failed"
        assert app.state.database_engine is None
        assert not paths.database_file.exists()
    finally:
        _remove_root(root, tmp_path)


def test_reparse_child_is_rejected_before_database_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "reparse-storage"
    settings = create_test_settings(data_root=root)
    paths = StoragePaths.from_settings(settings)

    monkeypatch.setattr(
        "aiwebnovel.storage.initializer.is_reparse_point",
        lambda path: path == paths.assets,
    )
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            ready = client.get("/api/v1/health/ready")
        assert ready.status_code == 503
        assert ready.json()["checks"]["storage"] == "failed"
        assert ready.json()["checks"]["database"] == "failed"
        assert not paths.database_file.exists()
        assert str(paths.assets) not in ready.text
    finally:
        _remove_root(root, tmp_path)


def test_application_instances_keep_storage_and_database_state_isolated(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first-root"
    second_root = tmp_path / "second-root"
    first = create_test_app(data_root=first_root)
    second = create_test_app(data_root=second_root)
    try:
        with TestClient(first) as first_client:
            assert first_client.get("/api/v1/health/ready").status_code == 200
            with first.state.database_engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE first_only (id INTEGER PRIMARY KEY)")

            with TestClient(second) as second_client:
                assert second_client.get("/api/v1/health/ready").status_code == 200
                assert first.state.storage_paths is not second.state.storage_paths
                assert first.state.database_engine is not second.state.database_engine
                assert "first_only" in inspect(first.state.database_engine).get_table_names()
                assert "first_only" not in inspect(second.state.database_engine).get_table_names()

            assert second.state.database_engine is None
            assert first.state.database_engine is not None

        assert first.state.database_engine is None
    finally:
        _remove_root(first_root, tmp_path)
        _remove_root(second_root, tmp_path)
