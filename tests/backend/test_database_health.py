"""Database readiness success, failure privacy, and app isolation tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import URL

from aiwebnovel.core.config import Settings
from aiwebnovel.core.middleware import is_valid_request_id
from aiwebnovel.db.health import DatabaseHealthError, check_database_health
from aiwebnovel.main import create_app

pytestmark = pytest.mark.integration


def _database_url(path: Path) -> str:
    return str(URL.create("sqlite+pysqlite", database=path.as_posix()))


def _settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        data_root=path.parent / f"{path.stem}-storage",
        database_url=_database_url(path),
    )


def _remove_sqlite_artifacts(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def test_health_check_rejects_unconfigured_sqlite_engine(tmp_path: Path) -> None:
    database_path = tmp_path / "unconfigured.sqlite3"
    engine = create_engine(_database_url(database_path))
    try:
        with pytest.raises(DatabaseHealthError):
            check_database_health(engine)
    finally:
        engine.dispose()
        _remove_sqlite_artifacts(database_path)


def test_ready_database_failure_is_private_while_live_stays_available(
    tmp_path: Path,
) -> None:
    database_target = tmp_path / "database-target-is-a-directory.sqlite3"
    database_target.mkdir()
    app = create_app(_settings(database_target))

    with TestClient(app) as client:
        live_response = client.get("/api/v1/health/live")
        ready_response = client.get(
            "/api/v1/health/ready",
            headers={"X-Request-ID": "database-failure-test"},
        )

    assert live_response.status_code == 200
    assert ready_response.status_code == 503
    assert ready_response.json() == {
        "status": "not_ready",
        "checks": {
            "configuration": "ok",
            "application": "ok",
            "storage": "ok",
            "database": "failed",
            "frontend": "not_required",
        },
    }
    assert ready_response.headers["X-Request-ID"] == "database-failure-test"
    assert is_valid_request_id(ready_response.headers["X-Request-ID"])
    assert str(database_target) not in ready_response.text
    assert database_target.name not in ready_response.text
    assert "OperationalError" not in ready_response.text
    assert "Traceback" not in ready_response.text
    assert not ({"codex", "model", "business"} & ready_response.json()["checks"].keys())


def test_application_does_not_run_migrations_automatically(tmp_path: Path) -> None:
    database_path = tmp_path / "no-auto-migration.sqlite3"
    app = create_app(_settings(database_path))

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")
        engine = app.state.database_engine
        health = check_database_health(engine)
        tables = inspect(engine).get_table_names()

    assert response.status_code == 200
    assert health.foreign_keys is True
    assert health.journal_mode == "wal"
    assert tables == []
    assert app.state.initialized is False
    _remove_sqlite_artifacts(database_path)


def test_application_instances_isolate_and_dispose_database_resources(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first-app.sqlite3"
    second_path = tmp_path / "second-app.sqlite3"
    first_app = create_app(_settings(first_path))
    second_app = create_app(_settings(second_path))
    disposed: list[str] = []

    with TestClient(first_app) as first_client:
        first_engine = first_app.state.database_engine
        first_factory = first_app.state.database_session_factory
        event.listen(
            first_engine,
            "engine_disposed",
            lambda _engine: disposed.append("first"),
        )
        assert first_client.get("/api/v1/health/ready").status_code == 200

        with TestClient(second_app) as second_client:
            second_engine = second_app.state.database_engine
            second_factory = second_app.state.database_session_factory
            event.listen(
                second_engine,
                "engine_disposed",
                lambda _engine: disposed.append("second"),
            )
            assert second_client.get("/api/v1/health/ready").status_code == 200

            assert first_engine is not second_engine
            assert first_factory is not second_factory
            with first_engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE first_app_only (id INTEGER PRIMARY KEY)")
            assert "first_app_only" in inspect(first_engine).get_table_names()
            assert "first_app_only" not in inspect(second_engine).get_table_names()

        assert second_app.state.database_engine is None
        assert second_app.state.database_session_factory is None

    assert first_app.state.database_engine is None
    assert first_app.state.database_session_factory is None
    assert sorted(disposed) == ["first", "second"]
    _remove_sqlite_artifacts(first_path)
    _remove_sqlite_artifacts(second_path)
