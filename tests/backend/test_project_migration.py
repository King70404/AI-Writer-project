"""Project migration cycle, schema inventory, and isolated database fixtures."""

import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from aiwebnovel.core.config import Settings
from aiwebnovel.db.engine import create_database_engine

pytestmark = pytest.mark.integration

_BASELINE_REVISION = "0001_initialize_database"
_PROJECT_REVISION = "0002_create_project_foundation"
_PROJECT_TABLES = {"projects", "project_revisions", "project_heads"}
_PROJECT_TRIGGERS = {
    "trg_project_revisions_no_update",
    "trg_project_revisions_no_delete",
}
_PROJECT_INDEX = "ix_project_revisions_project_id_revision_number"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_CONFIG = _REPOSITORY_ROOT / "backend" / "alembic.ini"


@dataclass(frozen=True, slots=True)
class MigratedProjectDatabase:
    """One migrated temporary database and its policy-configured engine."""

    path: Path
    engine: Engine


def _database_url(path: Path) -> str:
    return str(URL.create("sqlite+pysqlite", database=path.as_posix()))


def _storage_root(database_path: Path) -> Path:
    return database_path.parents[1] / f"{database_path.stem}-storage"


def _run_alembic(database_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["AIWEBNOVEL_DATA_ROOT"] = str(_storage_root(database_path))
    environment["AIWEBNOVEL_DATABASE_URL"] = _database_url(database_path)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(_ALEMBIC_CONFIG),
            *arguments,
        ],
        cwd=_REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _remove_database_and_storage(database_path: Path, tmp_path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)
    storage_root = _storage_root(database_path)
    if storage_root.exists():
        assert storage_root.is_relative_to(tmp_path)
        shutil.rmtree(storage_root)
    if database_path.parent.exists() and not any(database_path.parent.iterdir()):
        assert database_path.parent.is_relative_to(tmp_path)
        database_path.parent.rmdir()
    assert not storage_root.exists()
    assert not any(
        Path(f"{database_path}{suffix}").exists() for suffix in ("", "-wal", "-shm", "-journal")
    )


def _schema_inventory(path: Path) -> tuple[set[str], set[str], set[str], str]:
    with closing(sqlite3.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        triggers = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'index' AND name NOT LIKE 'sqlite_autoindex_%'"
            )
        }
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    return tables, triggers, indexes, str(version)


@contextmanager
def migrated_project_database_context(
    tmp_path: Path,
) -> Iterator[MigratedProjectDatabase]:
    """Create, migrate, and fully remove one task-owned SQLite database."""
    database_path = tmp_path / "migrated project" / "project.sqlite3"
    upgrade = _run_alembic(database_path, "upgrade", _PROJECT_REVISION)
    assert upgrade.returncode == 0, upgrade.stderr
    engine = create_database_engine(
        Settings(
            environment="test",
            data_root=_storage_root(database_path),
            database_url=_database_url(database_path),
        )
    )
    try:
        yield MigratedProjectDatabase(database_path, engine)
    finally:
        engine.dispose()
        _remove_database_and_storage(database_path, tmp_path)


@pytest.fixture(name="migrated_project_database")
def _migrated_project_database_fixture(
    tmp_path: Path,
) -> Iterator[MigratedProjectDatabase]:
    with migrated_project_database_context(tmp_path) as database:
        yield database


def test_project_migration_upgrade_downgrade_reupgrade_cycle(tmp_path: Path) -> None:
    database_path = tmp_path / "project migration cycle" / "cycle.sqlite3"
    try:
        baseline = _run_alembic(database_path, "upgrade", _BASELINE_REVISION)
        assert baseline.returncode == 0, baseline.stderr
        assert _schema_inventory(database_path) == (
            {"alembic_version"},
            set(),
            set(),
            _BASELINE_REVISION,
        )

        upgrade = _run_alembic(database_path, "upgrade", _PROJECT_REVISION)
        assert upgrade.returncode == 0, upgrade.stderr
        tables, triggers, indexes, version = _schema_inventory(database_path)
        assert tables == {"alembic_version", *_PROJECT_TABLES}
        assert triggers == _PROJECT_TRIGGERS
        assert indexes == {_PROJECT_INDEX}
        assert version == _PROJECT_REVISION
        with closing(sqlite3.connect(database_path)) as connection:
            assert all(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                for table in sorted(_PROJECT_TABLES)
            )

        downgrade = _run_alembic(database_path, "downgrade", _BASELINE_REVISION)
        assert downgrade.returncode == 0, downgrade.stderr
        assert _schema_inventory(database_path) == (
            {"alembic_version"},
            set(),
            set(),
            _BASELINE_REVISION,
        )

        reupgrade = _run_alembic(database_path, "upgrade", _PROJECT_REVISION)
        assert reupgrade.returncode == 0, reupgrade.stderr
        assert _schema_inventory(database_path) == (
            {"alembic_version", *_PROJECT_TABLES},
            _PROJECT_TRIGGERS,
            {_PROJECT_INDEX},
            _PROJECT_REVISION,
        )
    finally:
        _remove_database_and_storage(database_path, tmp_path)


def test_project_migration_offline_sql_has_no_file_side_effect(tmp_path: Path) -> None:
    database_path = tmp_path / "project offline" / "offline.sqlite3"
    data_root = _storage_root(database_path)

    result = _run_alembic(database_path, "upgrade", _PROJECT_REVISION, "--sql")

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE projects" in result.stdout
    assert "CREATE TABLE project_revisions" in result.stdout
    assert "CREATE TABLE project_heads" in result.stdout
    assert "CREATE TRIGGER trg_project_revisions_no_update" in result.stdout
    assert "CREATE TRIGGER trg_project_revisions_no_delete" in result.stdout
    assert _PROJECT_REVISION in result.stdout
    assert not database_path.parent.exists()
    assert not database_path.exists()
    assert not data_root.exists()
