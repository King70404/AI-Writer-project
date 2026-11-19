"""Explicit legacy upgrades preserve committed author data and recovery copies."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.engine import URL

import aiwebnovel.core.config as config_module
import aiwebnovel.db.ai_workflow_upgrade as upgrade_module
import aiwebnovel.storage.initializer as storage_module
from aiwebnovel.core.config import Settings
from aiwebnovel.db.ai_workflow_upgrade import (
    AIWorkflowUpgradeBusy,
    AIWorkflowUpgradeFailed,
    AIWorkflowUpgradeUnsupported,
    StorageUpgradeChecks,
)
from aiwebnovel.db.ai_workflow_upgrade import (
    upgrade_ai_workflow_database as _upgrade_database,
)
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
    STORY_CONTROL_TABLE_NAMES,
    STORY_MEMORY_TABLE_NAMES,
    TIMELINE_PROPOSAL_TABLE_NAMES,
    USAGE_TABLE_NAMES,
    WORKBENCH_TABLE_NAMES,
    WRITING_JOB_BUDGET_TABLE_NAMES,
    WRITING_JOB_SCENE_TABLE_NAMES,
    WRITING_JOB_TABLE_NAMES,
    WRITING_STUDIO_TABLE_NAMES,
)
from aiwebnovel.storage.initializer import initialize_storage
from aiwebnovel.storage.paths import StoragePaths

from .test_novel_structure_migration import _run_alembic

pytestmark = pytest.mark.integration
_OLD = "0006_add_chapter_manuscript_content"
_NEW = "0026_add_timeline_proposals"
_AUTHOR_TABLES = (
    BUSINESS_TABLE_NAMES
    - METHOD_VALIDATION_TABLE_NAMES
    - WRITING_JOB_SCENE_TABLE_NAMES
    - PLAN_PROPOSAL_TABLE_NAMES
    - FORESHADOW_PROPOSAL_TABLE_NAMES
    - CHAPTER_DRAFT_TABLE_NAMES
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


def test_studio_database_upgrade_preserves_existing_reference_and_rule_versions(legacy):
    migrated = _run_alembic(legacy.paths.database_file, "upgrade", "0008_add_writing_studio")
    assert migrated.returncode == 0, migrated.stderr
    with legacy.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO writing_references (id,project_id,status,version,attempts,payload) VALUES (?,?,?,?,?,?)",
            (
                "reference-fixture",
                "project-fixture",
                "ready",
                1,
                0,
                '{"text":"合成范文，不含作者内容"}',
            ),
        )
        connection.exec_driver_sql(
            "INSERT INTO writing_rule_versions (id,rule_id,project_id,version,reference_id,payload) VALUES (?,?,?,?,?,?)",
            (
                "rule-version",
                "rule-fixture",
                "project-fixture",
                1,
                "reference-fixture",
                '{"title":"已确认方法"}',
            ),
        )
    tables = ("writing_references", "writing_rule_versions", "chapter_plan_revisions")

    def snapshot(path):
        with closing(sqlite3.connect(path)) as connection:
            return {
                table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables
            }

    before = snapshot(legacy.paths.database_file)
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW
    assert snapshot(legacy.paths.database_file) == before
    backups = list(legacy.paths.backups.glob("before-ai-workflow-*.sqlite3"))
    assert len(backups) == 1
    assert _version(backups[0]) == "0008_add_writing_studio"
    assert snapshot(backups[0]) == before


def test_story_memory_database_upgrade_adds_empty_immutable_editorial_table(legacy):
    migrated = _run_alembic(legacy.paths.database_file, "upgrade", "0009_add_story_memory")
    assert migrated.returncode == 0, migrated.stderr
    before = _snapshot(legacy.paths.database_file)
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        memory = connection.execute("SELECT * FROM story_memory_revisions").fetchall()
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW
    assert _snapshot(legacy.paths.database_file) == before
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        assert connection.execute("SELECT * FROM story_memory_revisions").fetchall() == memory
        assert connection.execute(
            "SELECT count(*) FROM chapter_editorial_revisions"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name='chapter_editorial_revisions' ORDER BY name"
        ).fetchall() == [
            ("trg_chapter_editorial_revisions_no_delete",),
            ("trg_chapter_editorial_revisions_no_update",),
        ]
    backups = list(legacy.paths.backups.glob("before-ai-workflow-*.sqlite3"))
    assert len(backups) == 1
    assert _version(backups[0]) == "0009_add_story_memory"


def test_workbench_database_upgrade_adds_empty_settle_once_usage_ledger(legacy):
    migrated = _run_alembic(
        legacy.paths.database_file, "upgrade", "0010_add_chapter_editorial_states"
    )
    assert migrated.returncode == 0, migrated.stderr
    before = _snapshot(legacy.paths.database_file)
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW
    assert _snapshot(legacy.paths.database_file) == before
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        assert connection.execute("SELECT count(*) FROM model_usage_attempts").fetchone() == (0,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name='model_usage_attempts' ORDER BY name"
        ).fetchall() == [
            ("trg_model_usage_attempts_no_delete",),
            ("trg_model_usage_attempts_settle_once",),
        ]
    backups = list(legacy.paths.backups.glob("before-ai-workflow-*.sqlite3"))
    assert len(backups) == 1
    assert _version(backups[0]) == "0010_add_chapter_editorial_states"


def test_usage_database_upgrade_adds_empty_append_only_edit_and_budget_tables(legacy):
    migrated = _run_alembic(legacy.paths.database_file, "upgrade", "0011_add_model_usage_ledger")
    assert migrated.returncode == 0, migrated.stderr
    before = _snapshot(legacy.paths.database_file)
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW
    assert _snapshot(legacy.paths.database_file) == before
    tables = (
        "ai_candidate_edits",
        "ai_candidate_edit_adoptions",
        "model_price_revisions",
        "project_budget_revisions",
        "model_budget_reservations",
    )
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        for table in tables:
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
            assert connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=? ORDER BY name",
                (table,),
            ).fetchall() == [(f"trg_{table}_no_delete",), (f"trg_{table}_no_update",)]
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name='ai_workflow_candidates'"
        ).fetchall() == [("trg_ai_workflow_candidates_original_immutable",)]
    backups = list(legacy.paths.backups.glob("before-ai-workflow-*.sqlite3"))
    assert len(backups) == 1
    assert _version(backups[0]) == "0011_add_model_usage_ledger"


def test_budget_database_upgrade_adds_empty_append_only_story_control_table(legacy):
    migrated = _run_alembic(
        legacy.paths.database_file, "upgrade", "0012_add_candidate_edits_and_budgets"
    )
    assert migrated.returncode == 0, migrated.stderr
    before = _snapshot(legacy.paths.database_file)
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW
    assert _snapshot(legacy.paths.database_file) == before
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        assert connection.execute("SELECT count(*) FROM story_control_revisions").fetchone() == (0,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND tbl_name='story_control_revisions' ORDER BY name"
        ).fetchall() == [
            ("trg_story_control_revisions_no_delete",),
            ("trg_story_control_revisions_no_update",),
        ]
    backups = list(legacy.paths.backups.glob("before-ai-workflow-*.sqlite3"))
    assert len(backups) == 1
    assert _version(backups[0]) == "0012_add_candidate_edits_and_budgets"


def upgrade_ai_workflow_database(engine: Engine, paths: StoragePaths) -> None:
    _upgrade_database(
        engine,
        paths,
        StorageUpgradeChecks(
            storage_module.validate_storage_layout, storage_module.is_reparse_point
        ),
    )


@dataclass(frozen=True)
class LegacyDatabase:
    engine: Engine
    paths: StoragePaths


def test_method_migration_preserves_existing_usage_and_reservation_triggers(legacy):
    migrated = _run_alembic(legacy.paths.database_file, "upgrade", "0017_add_writing_job_budgets")
    assert migrated.returncode == 0, migrated.stderr
    with legacy.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO model_price_revisions VALUES ('price-old', 'profile', 1, 'CNY', 2000000, 4000000, '2026-01-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO model_usage_attempts (id,project_id,operation,task_id,profile_id,model_kind,model_name,input_characters,output_characters,status,usage_source,reported_input_tokens,reported_output_tokens,reported_total_tokens,started_at,finished_at,duration_ms) VALUES ('attempt-old','project-fixture','generation','task','profile','local','fake',10,5,'completed','provider_reported',100,10,110,'2026-01-01','2026-01-01',1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO model_budget_reservations VALUES ('attempt-old','project-fixture','task','price-old','CNY',100,10,500,'2026-01-01')"
        )
    migrated = _run_alembic(legacy.paths.database_file, "upgrade", "0019_add_cache_token_prices")
    assert migrated.returncode == 0, migrated.stderr
    with legacy.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO model_price_revisions (id,profile_id,version,currency,input_micros_per_million,output_micros_per_million,created_at,cached_input_micros_per_million,cache_write_micros_per_million) VALUES ('price-cache','profile',2,'CNY',2000000,4000000,'2026-01-01',500000,3000000)"
        )
        connection.exec_driver_sql(
            "INSERT INTO model_usage_attempts (id,project_id,operation,task_id,profile_id,model_kind,model_name,input_characters,output_characters,status,usage_source,reported_input_tokens,reported_output_tokens,reported_total_tokens,started_at,finished_at,duration_ms,cached_input_tokens,cache_write_tokens,cache_details_status) VALUES ('attempt-cache','project-fixture','generation','task-cache','profile','local','fake',10,5,'completed','provider_reported',100,10,110,'2026-01-01','2026-01-01',1,60,20,'reported')"
        )
        connection.exec_driver_sql(
            "INSERT INTO model_budget_reservations VALUES ('attempt-cache','project-fixture','task-cache','price-cache','CNY',100,10,500,'2026-01-01')"
        )
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        assert connection.execute(
            "SELECT cached_input_tokens,cache_write_tokens,cache_details_status FROM model_usage_attempts WHERE id='attempt-cache'"
        ).fetchone() == (60, 20, "reported")
        assert connection.execute(
            "SELECT cached_input_micros_per_million,cache_write_micros_per_million FROM model_price_revisions WHERE id='price-cache'"
        ).fetchone() == (500000, 3000000)
        assert connection.execute(
            "SELECT price_revision_id,reserved_micros FROM model_budget_reservations WHERE attempt_id='attempt-cache'"
        ).fetchone() == ("price-cache", 500)
        assert connection.execute(
            "SELECT operation,reported_input_tokens,reported_output_tokens FROM model_usage_attempts WHERE id='attempt-old'"
        ).fetchone() == ("generation", 100, 10)
        assert connection.execute(
            "SELECT cached_input_tokens,cache_write_tokens,cache_details_status FROM model_usage_attempts WHERE id='attempt-old'"
        ).fetchone() == (None, None, "not_reported")
        assert connection.execute(
            "SELECT input_micros_per_million,output_micros_per_million,cached_input_micros_per_million,cache_write_micros_per_million FROM model_price_revisions WHERE id='price-old'"
        ).fetchone() == (2000000, 4000000, None, None)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE model_usage_attempts SET cached_input_tokens=1 WHERE id='attempt-old'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE model_price_revisions SET cached_input_micros_per_million=1 WHERE id='price-old'"
            )
        assert connection.execute(
            "SELECT price_revision_id,reserved_micros FROM model_budget_reservations WHERE attempt_id='attempt-old'"
        ).fetchone() == ("price-old", 500)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE model_usage_attempts SET reported_input_tokens=1 WHERE id='attempt-old'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM model_budget_reservations WHERE attempt_id='attempt-old'"
            )


@pytest.fixture
def legacy(tmp_path: Path) -> Iterator[LegacyDatabase]:
    paths = StoragePaths.from_root(tmp_path / "owned author fixture")
    initialize_storage(paths)
    result = _run_alembic(paths.database_file, "upgrade", _OLD)
    assert result.returncode == 0, result.stderr
    settings = Settings(environment="test", data_root=paths.root, database_busy_timeout_ms=1)
    engine = create_database_engine(settings, storage_paths=paths)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO projects VALUES ('project-fixture', 1, '2026-01-01', '2026-01-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO project_revisions VALUES "
            "('revision-fixture', 'project-fixture', 1, ?, ?, '2026-01-01')",
            ("已有小说😀", "升级前保留的说明。"),
        )
        connection.exec_driver_sql(
            "INSERT INTO project_heads VALUES ('project-fixture', 'revision-fixture', '2026-01-01')"
        )
    try:
        yield LegacyDatabase(engine, paths)
    finally:
        engine.dispose()


def _snapshot(path: Path) -> tuple[dict[str, list[tuple]], list[tuple]]:
    with closing(sqlite3.connect(path)) as connection:
        data = {
            name: connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
            for name in sorted(_AUTHOR_TABLES)
        }
        objects = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' AND tbl_name NOT LIKE 'ai_workflow_%' "
            "AND tbl_name NOT IN ('writing_references', 'writing_rule_versions', 'chapter_plan_revisions', 'story_memory_revisions', 'chapter_editorial_revisions', 'model_usage_attempts', 'ai_candidate_edits', 'ai_candidate_edit_adoptions', 'model_price_revisions', 'project_budget_revisions', 'model_budget_reservations', 'story_control_revisions', 'import_previews', 'import_receipts', 'handoff_snapshots', 'external_candidates', 'writing_jobs', 'writing_job_budgets', 'writing_job_runs', 'method_trials', 'method_annotations', 'method_templates', 'writing_job_scene_marks', 'plan_proposals', 'foreshadow_proposals', 'chapter_drafts', 'timeline_proposals') ORDER BY name"
        ).fetchall()
        return data, objects


def _version(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        return connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_real_upgrade_preserves_author_rows_schema_and_backup_then_is_idempotent(legacy):
    original = _snapshot(legacy.paths.database_file)
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)

    assert _version(legacy.paths.database_file) == _NEW
    assert _snapshot(legacy.paths.database_file) == original
    backups = list(legacy.paths.backups.glob("before-ai-workflow-*.sqlite3"))
    assert len(backups) == 1
    assert _version(backups[0]) == _OLD
    assert _snapshot(backups[0]) == original
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert list(legacy.paths.backups.iterdir()) == backups
    assert _snapshot(legacy.paths.database_file) == original


def test_backup_includes_committed_wal_and_excludes_other_writers_until_migration_finishes(
    legacy, monkeypatch
):
    original_migrate = upgrade_module._migrate
    with closing(sqlite3.connect(legacy.paths.database_file, timeout=0)) as writer:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        writer.execute(
            "INSERT INTO project_revisions VALUES "
            "('wal-revision', 'project-fixture', 2, 'WAL 中已保存', '', '2026-01-02')"
        )
        writer.commit()
        assert Path(f"{legacy.paths.database_file}-wal").stat().st_size > 0
        expected = _snapshot(legacy.paths.database_file)

        def observe_writer_lock(connection: Connection) -> None:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                writer.execute("BEGIN IMMEDIATE")
            original_migrate(connection)

        monkeypatch.setattr(upgrade_module, "_migrate", observe_writer_lock)
        upgrade_ai_workflow_database(legacy.engine, legacy.paths)
        backup = next(legacy.paths.backups.glob("*.sqlite3"))
        assert _snapshot(backup) == expected
        assert _snapshot(legacy.paths.database_file) == expected
        writer.execute("BEGIN IMMEDIATE")
        writer.rollback()


def test_failed_migration_rolls_back_ddl_and_version_retains_backup_and_can_retry(
    legacy, monkeypatch
):
    original = _snapshot(legacy.paths.database_file)
    migrate = upgrade_module._migrate

    def fail_after_ddl(connection: Connection) -> None:
        migrate(connection)
        raise RuntimeError("private fixture details must not reach the author")

    monkeypatch.setattr(upgrade_module, "_migrate", fail_after_ddl)
    with pytest.raises(AIWorkflowUpgradeFailed, match="original data is retained") as error:
        upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert "private" not in str(error.value)
    assert _version(legacy.paths.database_file) == _OLD
    assert _snapshot(legacy.paths.database_file) == original
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'ai_workflow_%'"
            ).fetchall()
            == []
        )
    first_backup = next(legacy.paths.backups.glob("*.sqlite3"))
    assert _snapshot(first_backup) == original
    monkeypatch.setattr(upgrade_module, "_migrate", migrate)
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW
    assert first_backup.exists()
    assert len(list(legacy.paths.backups.glob("*.sqlite3"))) == 2


def test_failed_backup_flush_prevents_any_migration(legacy, monkeypatch):
    original = _snapshot(legacy.paths.database_file)

    def fail_flush(_descriptor: int) -> None:
        raise OSError("private disk path")

    monkeypatch.setattr(upgrade_module.os, "fsync", fail_flush)
    with pytest.raises(AIWorkflowUpgradeFailed, match="original data is retained"):
        upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _OLD
    assert _snapshot(legacy.paths.database_file) == original


def test_busy_database_has_no_backup_or_schema_changes(legacy):
    with legacy.engine.connect() as writer:
        writer.exec_driver_sql("BEGIN IMMEDIATE")
        with pytest.raises(AIWorkflowUpgradeBusy):
            upgrade_ai_workflow_database(legacy.engine, legacy.paths)
        writer.rollback()
    assert not list(legacy.paths.backups.iterdir())
    assert _version(legacy.paths.database_file) == _OLD


@pytest.mark.parametrize(
    "change",
    [
        "DROP TABLE alembic_version",
        "DELETE FROM alembic_version",
        "UPDATE alembic_version SET version_num='0005_create_novel_structure_foundation'",
        "CREATE TABLE unexpected (id INTEGER)",
        "DROP TABLE chapter_heads",
        "ALTER TABLE projects ADD COLUMN unexpected TEXT",
    ],
)
def test_unknown_or_incomplete_schema_is_rejected_without_backup_or_changes(legacy, change):
    with legacy.engine.begin() as connection:
        connection.exec_driver_sql(change)
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        before = list(connection.iterdump())
    with pytest.raises(AIWorkflowUpgradeUnsupported):
        upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert not list(legacy.paths.backups.iterdir())
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        assert list(connection.iterdump()) == before


def test_ready_version_with_incomplete_ai_columns_is_not_treated_as_ready(legacy):
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    with legacy.engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE ai_workflow_runs ADD COLUMN unexpected TEXT")
    with pytest.raises(AIWorkflowUpgradeUnsupported):
        upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert len(list(legacy.paths.backups.glob("*.sqlite3"))) == 1


@pytest.mark.parametrize("kind", ["memory", "outside", "query"])
def test_only_current_managed_database_url_is_accepted(legacy, tmp_path, kind):
    if kind == "memory":
        url = URL.create("sqlite+pysqlite", database=":memory:")
    elif kind == "outside":
        url = URL.create("sqlite+pysqlite", database=str(tmp_path / "other.sqlite3"))
    else:
        url = legacy.engine.url.set(query={"mode": "ro"})
    engine = create_engine(url)
    try:
        with pytest.raises(AIWorkflowUpgradeUnsupported):
            upgrade_ai_workflow_database(engine, legacy.paths)
    finally:
        engine.dispose()
    assert not (tmp_path / "other.sqlite3").exists()
    assert not list(legacy.paths.backups.iterdir())
    assert _version(legacy.paths.database_file) == _OLD


@pytest.mark.parametrize("redirect", ["database", "wal", "parent", "backup"])
def test_redirected_database_sidecar_ancestor_or_backup_is_rejected(legacy, monkeypatch, redirect):
    redirects = {
        "database": legacy.paths.database_file,
        "wal": Path(f"{legacy.paths.database_file}-wal"),
        "parent": legacy.paths.root.parent,
        "backup": legacy.paths.backups,
    }
    target = redirects[redirect]
    monkeypatch.setattr(storage_module, "is_reparse_point", lambda path: path == target)
    with pytest.raises(AIWorkflowUpgradeUnsupported):
        upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert not list(legacy.paths.backups.iterdir())
    assert _version(legacy.paths.database_file) == _OLD


def test_programmatic_alembic_uses_supplied_connection_without_loading_environment(
    legacy, monkeypatch
):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Must not select a database or initialize storage from environment")

    monkeypatch.setattr(config_module, "get_settings", forbidden)
    monkeypatch.setattr(storage_module, "initialize_storage", forbidden)
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW


def test_story_control_upgrade_preserves_data_and_adds_empty_import_tables(legacy):
    migrated = _run_alembic(legacy.paths.database_file, "upgrade", "0013_add_story_control")
    assert migrated.returncode == 0, migrated.stderr
    before = _snapshot(legacy.paths.database_file)
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW
    assert _snapshot(legacy.paths.database_file) == before
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        for table in sorted(IMPORT_TABLE_NAMES):
            assert connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone() == (0,)
    backup = next(legacy.paths.backups.glob("before-ai-workflow-*.sqlite3"))
    assert _version(backup) == "0013_add_story_control"
    assert _snapshot(backup) == before


def test_handoff_upgrade_preserves_data_and_adds_empty_writing_job_tables(legacy):
    migrated = _run_alembic(legacy.paths.database_file, "upgrade", "0015_add_external_handoffs")
    assert migrated.returncode == 0, migrated.stderr
    before = _snapshot(legacy.paths.database_file)
    upgrade_ai_workflow_database(legacy.engine, legacy.paths)
    assert _version(legacy.paths.database_file) == _NEW
    assert _snapshot(legacy.paths.database_file) == before
    with closing(sqlite3.connect(legacy.paths.database_file)) as connection:
        for table in sorted(WRITING_JOB_TABLE_NAMES | WRITING_JOB_BUDGET_TABLE_NAMES):
            assert connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone() == (0,)
    backup = next(legacy.paths.backups.glob("before-ai-workflow-*.sqlite3"))
    assert _version(backup) == "0015_add_external_handoffs"
    assert _snapshot(backup) == before
