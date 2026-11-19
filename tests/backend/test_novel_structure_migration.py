"""0005 migration cycle, schema inventory, constraints, and cleanup."""

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
from aiwebnovel.db.model_registry import (
    AI_WORKFLOW_TABLE_NAMES,
    BUSINESS_TABLE_NAMES,
    CANDIDATE_BUDGET_TABLE_NAMES,
    CHAPTER_DRAFT_TABLE_NAMES,
    FORESHADOW_PROPOSAL_TABLE_NAMES,
    HANDOFF_TABLE_NAMES,
    IMPORT_TABLE_NAMES,
    METHOD_VALIDATION_TABLE_NAMES,
    PLAN_PROPOSAL_TABLE_NAMES,
    SEMANTIC_INDEX_TABLE_NAMES,
    STORY_CONTROL_TABLE_NAMES,
    STORY_MEMORY_TABLE_NAMES,
    TIMELINE_PROPOSAL_TABLE_NAMES,
    USAGE_TABLE_NAMES,
    WORKBENCH_TABLE_NAMES,
    WRITING_JOB_BUDGET_TABLE_NAMES,
    WRITING_JOB_SCENE_TABLE_NAMES,
    WRITING_JOB_TABLE_NAMES,
    WRITING_STUDIO_TABLE_NAMES,
    load_model_metadata,
)

pytestmark = pytest.mark.integration

_PREVIOUS_REVISION = "0004_create_character_foundation"
_NOVEL_STRUCTURE_REVISION = "0005_create_novel_structure_foundation"
_CURRENT_NOVEL_STRUCTURE_REVISION = "0006_add_chapter_manuscript_content"
_PRE_AI_TABLE_NAMES = (
    BUSINESS_TABLE_NAMES
    - METHOD_VALIDATION_TABLE_NAMES
    - WRITING_JOB_SCENE_TABLE_NAMES
    - PLAN_PROPOSAL_TABLE_NAMES
    - FORESHADOW_PROPOSAL_TABLE_NAMES
    - CHAPTER_DRAFT_TABLE_NAMES
    - SEMANTIC_INDEX_TABLE_NAMES
    - TIMELINE_PROPOSAL_TABLE_NAMES
    - AI_WORKFLOW_TABLE_NAMES
    - WRITING_STUDIO_TABLE_NAMES
    - STORY_MEMORY_TABLE_NAMES
    - WORKBENCH_TABLE_NAMES
    - USAGE_TABLE_NAMES
    - CANDIDATE_BUDGET_TABLE_NAMES
    - STORY_CONTROL_TABLE_NAMES
    - IMPORT_TABLE_NAMES
    - HANDOFF_TABLE_NAMES
    - WRITING_JOB_TABLE_NAMES
    - WRITING_JOB_BUDGET_TABLE_NAMES
)
_NEW_TABLES = {
    "outlines",
    "outline_revisions",
    "outline_heads",
    "volumes",
    "volume_revisions",
    "volume_heads",
    "chapters",
    "chapter_revisions",
    "chapter_heads",
}
_NEW_TRIGGERS = {
    f"trg_{table}_no_{operation}"
    for table in ("outline_revisions", "volume_revisions", "chapter_revisions")
    for operation in ("update", "delete")
}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_CONFIG = _REPOSITORY_ROOT / "backend" / "alembic.ini"


@dataclass(frozen=True, slots=True)
class MigratedNovelStructureDatabase:
    path: Path
    engine: Engine


def _database_url(path: Path) -> str:
    return str(URL.create("sqlite+pysqlite", database=path.as_posix()))


def _storage_root(path: Path) -> Path:
    return path.parents[1] / f"{path.stem}-storage"


def _run_alembic(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["AIWEBNOVEL_DATA_ROOT"] = str(_storage_root(path))
    environment["AIWEBNOVEL_DATABASE_URL"] = _database_url(path)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_CONFIG), *arguments],
        cwd=_REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _cleanup(path: Path, tmp_path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    storage = _storage_root(path)
    if storage.exists():
        assert storage.is_relative_to(tmp_path)
        shutil.rmtree(storage)
    if path.parent.exists() and not any(path.parent.iterdir()):
        path.parent.rmdir()


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
def migrated_novel_structure_database_context(
    tmp_path: Path,
) -> Iterator[MigratedNovelStructureDatabase]:
    path = tmp_path / "novel structure" / "structure.sqlite3"
    upgrade = _run_alembic(path, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
    engine = create_database_engine(
        Settings(
            environment="test",
            data_root=_storage_root(path),
            database_url=_database_url(path),
        )
    )
    try:
        yield MigratedNovelStructureDatabase(path, engine)
    finally:
        engine.dispose()
        _cleanup(path, tmp_path)


@pytest.fixture(name="migrated_novel_structure_database")
def _migrated_database_fixture(
    tmp_path: Path,
) -> Iterator[MigratedNovelStructureDatabase]:
    with migrated_novel_structure_database_context(tmp_path) as database:
        yield database


def test_metadata_registers_authorized_tables_with_unchanged_author_schema() -> None:
    metadata = load_model_metadata()

    assert len(BUSINESS_TABLE_NAMES) == 49
    assert len(_PRE_AI_TABLE_NAMES) == 18
    assert frozenset(metadata.tables) == BUSINESS_TABLE_NAMES
    assert _NEW_TABLES <= BUSINESS_TABLE_NAMES
    assert {table: set(metadata.tables[table].columns.keys()) for table in _NEW_TABLES} == {
        "outlines": {"id", "project_id", "concurrency_version", "created_at", "updated_at"},
        "outline_revisions": {
            "id",
            "outline_id",
            "revision_number",
            "title",
            "summary",
            "created_at",
        },
        "outline_heads": {"outline_id", "revision_id", "updated_at"},
        "volumes": {
            "id",
            "project_id",
            "current_position",
            "concurrency_version",
            "created_at",
            "updated_at",
        },
        "volume_revisions": {
            "id",
            "volume_id",
            "revision_number",
            "title",
            "summary",
            "position",
            "created_at",
        },
        "volume_heads": {"volume_id", "revision_id", "updated_at"},
        "chapters": {
            "id",
            "project_id",
            "volume_id",
            "current_position",
            "concurrency_version",
            "created_at",
            "updated_at",
        },
        "chapter_revisions": {
            "id",
            "chapter_id",
            "revision_number",
            "title",
            "summary",
            "position",
            "content",
            "created_at",
        },
        "chapter_heads": {"chapter_id", "revision_id", "updated_at"},
    }


def test_0005_upgrade_downgrade_reupgrade_cycle(tmp_path: Path) -> None:
    path = tmp_path / "migration cycle" / "cycle.sqlite3"
    try:
        previous = _run_alembic(path, "upgrade", _PREVIOUS_REVISION)
        assert previous.returncode == 0, previous.stderr
        old_tables, old_triggers, old_version = _inventory(path)

        upgrade = _run_alembic(path, "upgrade", _NOVEL_STRUCTURE_REVISION)
        assert upgrade.returncode == 0, upgrade.stderr
        tables, triggers, version = _inventory(path)
        assert tables == {"alembic_version", *_PRE_AI_TABLE_NAMES}
        assert len(_PRE_AI_TABLE_NAMES) == 18
        assert triggers == old_triggers | _NEW_TRIGGERS
        assert len(triggers) == 12
        assert version == _NOVEL_STRUCTURE_REVISION

        downgrade = _run_alembic(path, "downgrade", _PREVIOUS_REVISION)
        assert downgrade.returncode == 0, downgrade.stderr
        assert _inventory(path) == (old_tables, old_triggers, old_version)

        reupgrade = _run_alembic(path, "upgrade", _NOVEL_STRUCTURE_REVISION)
        assert reupgrade.returncode == 0, reupgrade.stderr
        tables, triggers, version = _inventory(path)
        assert tables == {"alembic_version", *_PRE_AI_TABLE_NAMES}
        assert triggers == old_triggers | _NEW_TRIGGERS
        assert version == _NOVEL_STRUCTURE_REVISION
    finally:
        _cleanup(path, tmp_path)


def test_0005_offline_sql_has_no_file_side_effect(tmp_path: Path) -> None:
    path = tmp_path / "offline" / "offline.sqlite3"
    result = _run_alembic(path, "upgrade", _NOVEL_STRUCTURE_REVISION, "--sql")

    assert result.returncode == 0, result.stderr
    for table in sorted(_NEW_TABLES):
        assert f"CREATE TABLE {table}" in result.stdout
    for trigger in sorted(_NEW_TRIGGERS):
        assert f"CREATE TRIGGER {trigger}" in result.stdout
    assert not path.exists()
    assert not path.parent.exists()
    assert not _storage_root(path).exists()


def test_0006_preserves_old_chapter_revisions_across_migration_cycle(
    tmp_path: Path,
) -> None:
    path = tmp_path / "manuscript migration" / "cycle.sqlite3"
    old_row = (
        "chv_00000000000000000000000001",
        "chp_00000000000000000000000001",
        1,
        "Existing chapter",
        "Existing summary",
        2,
        "2026-08-31 01:02:03.000000",
    )
    try:
        previous = _run_alembic(path, "upgrade", _NOVEL_STRUCTURE_REVISION)
        assert previous.returncode == 0, previous.stderr
        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                "INSERT INTO chapter_revisions "
                "(id, chapter_id, revision_number, title, summary, position, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                old_row,
            )
            connection.commit()

        upgrade = _run_alembic(path, "upgrade", _CURRENT_NOVEL_STRUCTURE_REVISION)
        assert upgrade.returncode == 0, upgrade.stderr
        with closing(sqlite3.connect(path)) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info('chapter_revisions')")
            }
            migrated = connection.execute(
                "SELECT id, chapter_id, revision_number, title, summary, position, "
                "created_at, content FROM chapter_revisions"
            ).fetchone()
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute("UPDATE chapter_revisions SET content = 'changed'")
        tables, triggers, version = _inventory(path)
        assert len(tables) == 19
        assert len(triggers) == 12
        assert version == _CURRENT_NOVEL_STRUCTURE_REVISION
        assert "content" in columns
        assert migrated == (*old_row, "")

        downgrade = _run_alembic(path, "downgrade", _NOVEL_STRUCTURE_REVISION)
        assert downgrade.returncode == 0, downgrade.stderr
        with closing(sqlite3.connect(path)) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info('chapter_revisions')")
            }
            restored = connection.execute(
                "SELECT id, chapter_id, revision_number, title, summary, position, "
                "created_at FROM chapter_revisions"
            ).fetchone()
        assert "content" not in columns
        assert restored == old_row
        assert _inventory(path)[1:] == (triggers, _NOVEL_STRUCTURE_REVISION)

        reupgrade = _run_alembic(path, "upgrade", _CURRENT_NOVEL_STRUCTURE_REVISION)
        assert reupgrade.returncode == 0, reupgrade.stderr
        with closing(sqlite3.connect(path)) as connection:
            remigrated = connection.execute(
                "SELECT id, chapter_id, revision_number, title, summary, position, "
                "created_at, content FROM chapter_revisions"
            ).fetchone()
        assert remigrated == (*old_row, "")
        assert _inventory(path)[1:] == (triggers, _CURRENT_NOVEL_STRUCTURE_REVISION)
    finally:
        _cleanup(path, tmp_path)


def test_0005_constraints_foreign_keys_indexes_and_wal(
    migrated_novel_structure_database: MigratedNovelStructureDatabase,
) -> None:
    with closing(sqlite3.connect(migrated_novel_structure_database.path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        schema = "\n".join(
            row[0]
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND "
                "(name LIKE 'outline%' OR name LIKE 'volume%' OR name LIKE 'chapter%')"
            )
            if row[0] is not None
        )
        indexes = {
            row[1]
            for table in ("volumes", "chapters")
            for row in connection.execute(f"PRAGMA index_list('{table}')")
        }
        foreign_tables = {
            row[2]
            for table in _NEW_TABLES
            for row in connection.execute(f"PRAGMA foreign_key_list('{table}')")
        }

    for constraint in (
        "uq_outlines_project_id",
        "uq_volumes_project_position",
        "uq_chapters_volume_position",
        "uq_outline_revisions_owner_number",
        "uq_volume_revisions_owner_number",
        "uq_chapter_revisions_owner_number",
        "fk_outline_heads_revision_owner",
        "fk_volume_heads_revision_owner",
        "fk_chapter_heads_revision_owner",
    ):
        assert constraint in schema
    assert {"ix_volumes_project_id", "ix_chapters_project_id", "ix_chapters_volume_id"} <= indexes
    assert {"projects", "outlines", "volumes", "chapters"} <= foreign_tables
