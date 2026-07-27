"""Story Bible migration cycle, exact schema, triggers, and cleanup."""

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

_PROJECT_REVISION = "0002_create_project_foundation"
_STORY_BIBLE_REVISION = "0003_create_story_bible_foundation"
_PROJECT_TABLES = {"projects", "project_revisions", "project_heads"}
_STORY_BIBLE_TABLES = {
    "story_bibles",
    "story_bible_revisions",
    "story_bible_heads",
}
_PROJECT_TRIGGERS = {
    "trg_project_revisions_no_update",
    "trg_project_revisions_no_delete",
}
_STORY_BIBLE_TRIGGERS = {
    "trg_story_bible_revisions_no_update",
    "trg_story_bible_revisions_no_delete",
}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_CONFIG = _REPOSITORY_ROOT / "backend" / "alembic.ini"


@dataclass(frozen=True, slots=True)
class MigratedStoryBibleDatabase:
    """One fully migrated isolated SQLite database."""

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


def _inventory(path: Path) -> tuple[set[str], set[str], str]:
    with closing(sqlite3.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        triggers = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        version = str(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0])
    return tables, triggers, version


@contextmanager
def migrated_story_bible_database_context(
    tmp_path: Path,
) -> Iterator[MigratedStoryBibleDatabase]:
    """Migrate, expose, dispose, and remove one task-owned database."""
    database_path = tmp_path / "migrated story bible" / "story-bible.sqlite3"
    upgrade = _run_alembic(database_path, "upgrade", _STORY_BIBLE_REVISION)
    assert upgrade.returncode == 0, upgrade.stderr
    engine = create_database_engine(
        Settings(
            environment="test",
            data_root=_storage_root(database_path),
            database_url=_database_url(database_path),
        )
    )
    try:
        yield MigratedStoryBibleDatabase(database_path, engine)
    finally:
        engine.dispose()
        _remove_database_and_storage(database_path, tmp_path)


@pytest.fixture(name="migrated_story_bible_database")
def _migrated_story_bible_database_fixture(
    tmp_path: Path,
) -> Iterator[MigratedStoryBibleDatabase]:
    with migrated_story_bible_database_context(tmp_path) as database:
        yield database


def test_story_bible_migration_upgrade_downgrade_reupgrade_cycle(tmp_path: Path) -> None:
    database_path = tmp_path / "story bible migration cycle" / "cycle.sqlite3"
    try:
        project = _run_alembic(database_path, "upgrade", _PROJECT_REVISION)
        assert project.returncode == 0, project.stderr
        assert _inventory(database_path) == (
            {"alembic_version", *_PROJECT_TABLES},
            _PROJECT_TRIGGERS,
            _PROJECT_REVISION,
        )

        upgrade = _run_alembic(database_path, "upgrade", _STORY_BIBLE_REVISION)
        assert upgrade.returncode == 0, upgrade.stderr
        assert _inventory(database_path) == (
            {"alembic_version", *_PROJECT_TABLES, *_STORY_BIBLE_TABLES},
            _PROJECT_TRIGGERS | _STORY_BIBLE_TRIGGERS,
            _STORY_BIBLE_REVISION,
        )

        downgrade = _run_alembic(database_path, "downgrade", _PROJECT_REVISION)
        assert downgrade.returncode == 0, downgrade.stderr
        assert _inventory(database_path) == (
            {"alembic_version", *_PROJECT_TABLES},
            _PROJECT_TRIGGERS,
            _PROJECT_REVISION,
        )

        reupgrade = _run_alembic(database_path, "upgrade", _STORY_BIBLE_REVISION)
        assert reupgrade.returncode == 0, reupgrade.stderr
        assert _inventory(database_path) == (
            {"alembic_version", *_PROJECT_TABLES, *_STORY_BIBLE_TABLES},
            _PROJECT_TRIGGERS | _STORY_BIBLE_TRIGGERS,
            _STORY_BIBLE_REVISION,
        )
        with closing(sqlite3.connect(database_path)) as connection:
            assert all(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                for table in sorted(_STORY_BIBLE_TABLES)
            )
    finally:
        _remove_database_and_storage(database_path, tmp_path)


def test_story_bible_offline_migration_has_no_file_side_effect(tmp_path: Path) -> None:
    database_path = tmp_path / "story bible offline" / "offline.sqlite3"
    result = _run_alembic(
        database_path,
        "upgrade",
        _STORY_BIBLE_REVISION,
        "--sql",
    )

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE story_bibles" in result.stdout
    assert "CREATE TABLE story_bible_revisions" in result.stdout
    assert "CREATE TABLE story_bible_heads" in result.stdout
    assert "CREATE TRIGGER trg_story_bible_revisions_no_update" in result.stdout
    assert "CREATE TRIGGER trg_story_bible_revisions_no_delete" in result.stdout
    assert _STORY_BIBLE_REVISION in result.stdout
    assert not database_path.parent.exists()
    assert not database_path.exists()
    assert not _storage_root(database_path).exists()
