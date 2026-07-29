"""Character migration cycle, exact schema, triggers, and cleanup."""

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

_INITIAL_REVISION = "0001_initialize_database"
_PROJECT_REVISION = "0002_create_project_foundation"
_STORY_BIBLE_REVISION = "0003_create_story_bible_foundation"
_CHARACTER_REVISION = "0004_create_character_foundation"
_PROJECT_TABLES = {"projects", "project_revisions", "project_heads"}
_STORY_BIBLE_TABLES = {
    "story_bibles",
    "story_bible_revisions",
    "story_bible_heads",
}
_CHARACTER_TABLES = {"characters", "character_revisions", "character_heads"}
_PROJECT_TRIGGERS = {
    "trg_project_revisions_no_update",
    "trg_project_revisions_no_delete",
}
_STORY_BIBLE_TRIGGERS = {
    "trg_story_bible_revisions_no_update",
    "trg_story_bible_revisions_no_delete",
}
_CHARACTER_TRIGGERS = {
    "trg_character_revisions_no_update",
    "trg_character_revisions_no_delete",
}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_CONFIG = _REPOSITORY_ROOT / "backend" / "alembic.ini"


@dataclass(frozen=True, slots=True)
class MigratedCharacterDatabase:
    """One fully migrated isolated SQLite database."""

    path: Path
    engine: Engine


def _database_url(path: Path) -> str:
    return str(URL.create("sqlite+pysqlite", database=path.as_posix()))


def _storage_root(database_path: Path) -> Path:
    return database_path.parents[1] / f"{database_path.stem}-storage"


def _run_alembic(
    database_path: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
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


def _inventory(path: Path) -> tuple[set[str], set[str], set[str], str]:
    with closing(sqlite3.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        triggers = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
            )
        }
        version = str(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0])
    return tables, triggers, indexes, version


@contextmanager
def migrated_character_database_context(
    tmp_path: Path,
) -> Iterator[MigratedCharacterDatabase]:
    """Migrate, expose, dispose, and remove one task-owned database."""
    database_path = tmp_path / "migrated character" / "character.sqlite3"
    upgrade = _run_alembic(database_path, "upgrade", _CHARACTER_REVISION)
    assert upgrade.returncode == 0, upgrade.stderr
    engine = create_database_engine(
        Settings(
            environment="test",
            data_root=_storage_root(database_path),
            database_url=_database_url(database_path),
        )
    )
    try:
        yield MigratedCharacterDatabase(database_path, engine)
    finally:
        engine.dispose()
        _remove_database_and_storage(database_path, tmp_path)


@pytest.fixture(name="migrated_character_database")
def _migrated_character_database_fixture(
    tmp_path: Path,
) -> Iterator[MigratedCharacterDatabase]:
    with migrated_character_database_context(tmp_path) as database:
        yield database


def test_character_migration_upgrade_downgrade_reupgrade_cycle(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "character migration cycle" / "cycle.sqlite3"
    try:
        initial = _run_alembic(database_path, "upgrade", _INITIAL_REVISION)
        assert initial.returncode == 0, initial.stderr
        project = _run_alembic(database_path, "upgrade", _PROJECT_REVISION)
        assert project.returncode == 0, project.stderr
        story_bible = _run_alembic(
            database_path,
            "upgrade",
            _STORY_BIBLE_REVISION,
        )
        assert story_bible.returncode == 0, story_bible.stderr

        upgrade = _run_alembic(database_path, "upgrade", _CHARACTER_REVISION)
        assert upgrade.returncode == 0, upgrade.stderr
        tables, triggers, indexes, version = _inventory(database_path)
        assert tables == {
            "alembic_version",
            *_PROJECT_TABLES,
            *_STORY_BIBLE_TABLES,
            *_CHARACTER_TABLES,
        }
        assert triggers == (_PROJECT_TRIGGERS | _STORY_BIBLE_TRIGGERS | _CHARACTER_TRIGGERS)
        assert "ix_characters_project_id" in indexes
        assert version == _CHARACTER_REVISION

        downgrade = _run_alembic(
            database_path,
            "downgrade",
            _STORY_BIBLE_REVISION,
        )
        assert downgrade.returncode == 0, downgrade.stderr
        tables, triggers, indexes, version = _inventory(database_path)
        assert tables == {
            "alembic_version",
            *_PROJECT_TABLES,
            *_STORY_BIBLE_TABLES,
        }
        assert triggers == _PROJECT_TRIGGERS | _STORY_BIBLE_TRIGGERS
        assert "ix_characters_project_id" not in indexes
        assert version == _STORY_BIBLE_REVISION

        reupgrade = _run_alembic(database_path, "upgrade", _CHARACTER_REVISION)
        assert reupgrade.returncode == 0, reupgrade.stderr
        tables, triggers, indexes, version = _inventory(database_path)
        assert tables == {
            "alembic_version",
            *_PROJECT_TABLES,
            *_STORY_BIBLE_TABLES,
            *_CHARACTER_TABLES,
        }
        assert triggers == (_PROJECT_TRIGGERS | _STORY_BIBLE_TRIGGERS | _CHARACTER_TRIGGERS)
        assert "ix_characters_project_id" in indexes
        assert version == _CHARACTER_REVISION
        with closing(sqlite3.connect(database_path)) as connection:
            assert all(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
                for table in sorted(_CHARACTER_TABLES)
            )
    finally:
        _remove_database_and_storage(database_path, tmp_path)


def test_character_offline_migration_has_no_file_side_effect(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "character offline" / "offline.sqlite3"
    result = _run_alembic(
        database_path,
        "upgrade",
        _CHARACTER_REVISION,
        "--sql",
    )

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE characters" in result.stdout
    assert "CREATE TABLE character_revisions" in result.stdout
    assert "CREATE TABLE character_heads" in result.stdout
    assert "CREATE INDEX ix_characters_project_id" in result.stdout
    assert "CREATE TRIGGER trg_character_revisions_no_update" in result.stdout
    assert "CREATE TRIGGER trg_character_revisions_no_delete" in result.stdout
    assert _CHARACTER_REVISION in result.stdout
    assert not database_path.parent.exists()
    assert not database_path.exists()
    assert not _storage_root(database_path).exists()


def test_character_constraints_foreign_keys_index_and_wal(
    migrated_character_database: MigratedCharacterDatabase,
) -> None:
    with closing(sqlite3.connect(migrated_character_database.path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = {
            (row[2], row[3], row[4], row[5], row[6])
            for table in ("characters", "character_revisions", "character_heads")
            for row in connection.execute(f"PRAGMA foreign_key_list('{table}')")
        }
        project_indexes = list(connection.execute("PRAGMA index_list('characters')"))
        schema_sql = "\n".join(
            row[0]
            for row in connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name LIKE 'character%' ORDER BY name"
            )
            if row[0] is not None
        )

    assert journal_mode == "wal"
    assert ("projects", "project_id", "id", "RESTRICT", "RESTRICT") in foreign_keys
    assert ("characters", "character_id", "id", "RESTRICT", "RESTRICT") in foreign_keys
    assert ("character_revisions", "revision_id", "id", "RESTRICT", "RESTRICT") in foreign_keys
    assert (
        "character_revisions",
        "character_id",
        "character_id",
        "RESTRICT",
        "RESTRICT",
    ) in foreign_keys
    assert any(row[1] == "ix_characters_project_id" and row[2] == 0 for row in project_indexes)
    for constraint_name in (
        "ck_characters_concurrency_version_positive",
        "ck_characters_updated_at_not_before_created_at",
        "ck_character_revisions_revision_number_positive",
        "ck_character_revisions_name_length",
        "ck_character_revisions_name_not_blank",
        "ck_character_revisions_role_length",
        "ck_character_revisions_profile_length",
        "uq_character_revisions_owner_revision_number",
        "uq_character_revisions_owner_id",
    ):
        assert constraint_name in schema_sql
