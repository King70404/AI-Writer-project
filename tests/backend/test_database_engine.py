"""SQLite engine, PRAGMA, import-side-effect, and foreign-key tests."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from aiwebnovel.core.config import Settings
from aiwebnovel.db.base import Base
from aiwebnovel.db.engine import create_database_engine
from aiwebnovel.main import create_app


def _database_url(path: Path) -> str:
    return str(URL.create("sqlite+pysqlite", database=path.as_posix()))


def _settings(path: Path, busy_timeout_ms: int = 3210) -> Settings:
    return Settings(
        environment="test",
        database_url=_database_url(path),
        database_busy_timeout_ms=busy_timeout_ms,
    )


def _remove_sqlite_artifacts(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def test_importing_database_modules_and_main_has_no_database_side_effect(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "含 空格" / "import-only.sqlite3"
    environment = os.environ.copy()
    environment["AIWEBNOVEL_DATABASE_URL"] = _database_url(database_path)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    repository_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import aiwebnovel.db.base; import aiwebnovel.db.engine; "
                "import aiwebnovel.db.session; import aiwebnovel.db.health; "
                "import aiwebnovel.main; "
                "print(len(aiwebnovel.db.base.Base.metadata.tables))"
            ),
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0"
    assert not database_path.parent.exists()
    assert not database_path.exists()


def test_create_app_has_no_engine_or_directory_before_lifespan(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "not-started" / "application.sqlite3"

    app = create_app(_settings(database_path))

    assert app.state.database_engine is None
    assert app.state.database_session_factory is None
    assert app.state.initialized is False
    assert not database_path.parent.exists()
    assert not database_path.exists()
    assert Base.metadata.tables == {}


def test_file_engine_enforces_required_pragmas_and_releases_file(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "含 空格" / "engine.sqlite3"
    engine = create_database_engine(_settings(database_path))

    assert database_path.parent.is_dir()
    assert not database_path.exists()
    try:
        with engine.connect() as first, engine.connect() as second:
            assert first.exec_driver_sql("SELECT 1").scalar_one() == 1
            assert first.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert second.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert (
                str(first.exec_driver_sql("PRAGMA journal_mode").scalar_one()).lower()
                == "wal"
            )
            assert first.exec_driver_sql("PRAGMA synchronous").scalar_one() == 1
            assert first.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 3210
            assert engine.pool.checkedout() == 2

        assert engine.pool.checkedout() == 0
        assert database_path.exists()
        assert inspect(engine).get_table_names() == []
    finally:
        engine.dispose()

    database_path.unlink()
    _remove_sqlite_artifacts(database_path)
    assert not database_path.exists()


def test_foreign_key_enforcement_rejects_orphan_rows_on_new_connections(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "foreign-keys.sqlite3"
    engine = create_database_engine(_settings(database_path))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE parent (id INTEGER PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE child ("
                "id INTEGER PRIMARY KEY, "
                "parent_id INTEGER NOT NULL REFERENCES parent(id))"
            )
            connection.exec_driver_sql("INSERT INTO parent (id) VALUES (1)")
            connection.exec_driver_sql(
                "INSERT INTO child (id, parent_id) VALUES (1, 1)"
            )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO child (id, parent_id) VALUES (2, 999)"
                )

        engine.dispose()
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                assert connection.exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar_one() == 1
                connection.exec_driver_sql(
                    "INSERT INTO child (id, parent_id) VALUES (3, 999)"
                )

        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM child"
            ).scalar_one() == 1
    finally:
        engine.dispose()
        _remove_sqlite_artifacts(database_path)


def test_memory_database_does_not_claim_wal_mode() -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        database_busy_timeout_ms=876,
    )
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 876
            assert str(
                connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
            ).lower() == "memory"
    finally:
        engine.dispose()
