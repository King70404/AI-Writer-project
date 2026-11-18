"""Project record shape, deterministic registration, and explicit mapper tests."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect

from aiwebnovel.db.base import Base
from aiwebnovel.db.model_registry import (
    AI_WORKFLOW_TABLE_NAMES,
    BUSINESS_TABLE_NAMES,
    CANDIDATE_BUDGET_TABLE_NAMES,
    CHARACTER_TABLE_NAMES,
    IMPORT_TABLE_NAMES,
    NOVEL_STRUCTURE_TABLE_NAMES,
    PROJECT_TABLE_NAMES,
    STORY_BIBLE_TABLE_NAMES,
    STORY_CONTROL_TABLE_NAMES,
    STORY_MEMORY_TABLE_NAMES,
    USAGE_TABLE_NAMES,
    WORKBENCH_TABLE_NAMES,
    WRITING_STUDIO_TABLE_NAMES,
    load_model_metadata,
)
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.entities import Project, ProjectAggregate, ProjectHead, ProjectRevision
from aiwebnovel.project.errors import InvalidProjectState
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.mappers import (
    project_aggregate_from_records,
    project_aggregate_to_records,
    project_from_record,
    project_head_from_record,
    project_head_to_record,
    project_revision_from_record,
    project_revision_to_record,
    project_to_record,
)
from aiwebnovel.project.persistence.models import (
    ProjectHeadRecord,
    ProjectRecord,
    ProjectRevisionRecord,
)
from aiwebnovel.project.transitions import create_initial_project
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)


def _project_id(value: int) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_int(value))


def _revision_id(value: int) -> ProjectRevisionId:
    return ProjectRevisionId.from_ulid(Ulid.from_int(value))


def _aggregate() -> ProjectAggregate:
    return create_initial_project(
        "  测试 Project  ",
        "first\r\nrevision",
        clock=lambda: _NOW,
        project_id_factory=lambda: _project_id(1),
        revision_id_factory=lambda: _revision_id(2),
    )


def test_model_registry_is_exact_idempotent_and_uses_shared_metadata() -> None:
    first = load_model_metadata()
    second = load_model_metadata()

    assert first is Base.metadata
    assert second is first
    assert frozenset(first.tables) == BUSINESS_TABLE_NAMES
    assert PROJECT_TABLE_NAMES < BUSINESS_TABLE_NAMES
    assert STORY_BIBLE_TABLE_NAMES < BUSINESS_TABLE_NAMES
    assert CHARACTER_TABLE_NAMES < BUSINESS_TABLE_NAMES
    assert NOVEL_STRUCTURE_TABLE_NAMES < BUSINESS_TABLE_NAMES
    assert set(first.tables) == {
        "projects",
        "project_revisions",
        "project_heads",
        "story_bibles",
        "story_bible_revisions",
        "story_bible_heads",
        "characters",
        "character_revisions",
        "character_heads",
        *NOVEL_STRUCTURE_TABLE_NAMES,
        *AI_WORKFLOW_TABLE_NAMES,
        *WRITING_STUDIO_TABLE_NAMES,
        *STORY_MEMORY_TABLE_NAMES,
        *WORKBENCH_TABLE_NAMES,
        *USAGE_TABLE_NAMES,
        *CANDIDATE_BUDGET_TABLE_NAMES,
        *STORY_CONTROL_TABLE_NAMES,
        *IMPORT_TABLE_NAMES,
        "external_candidates",
        "handoff_snapshots",
        "writing_job_budgets",
        "writing_job_runs",
        "writing_jobs",
        "method_trials",
        "method_annotations",
        "method_templates",
        "writing_job_scene_marks",
        "plan_proposals",
    }
    assert "alembic_version" not in first.tables
    assert all(table.metadata is first for table in first.tables.values())


def test_domain_import_does_not_register_models_or_create_database(tmp_path: Path) -> None:
    database_path = tmp_path / "import-only.sqlite3"
    environment = os.environ.copy()
    environment["AIWEBNOVEL_DATABASE_URL"] = f"sqlite+pysqlite:///{database_path.as_posix()}"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    repository_root = Path(__file__).resolve().parents[2]
    script = (
        "from aiwebnovel.db.base import Base; "
        "import aiwebnovel.project; "
        "print(','.join(sorted(Base.metadata.tables))); "
        "from aiwebnovel.db.model_registry import load_model_metadata; "
        "print(','.join(sorted(load_model_metadata().tables)))"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "",
        (
            "ai_candidate_edit_adoptions,ai_candidate_edits,ai_workflow_candidates,ai_workflow_runs,"
            "chapter_editorial_revisions,chapter_heads,chapter_plan_revisions,chapter_revisions,chapters,"
            "character_heads,character_revisions,characters,external_candidates,handoff_snapshots,import_previews,import_receipts,"
            "method_annotations,method_templates,method_trials,model_budget_reservations,model_price_revisions,model_usage_attempts,"
            "outline_heads,outline_revisions,outlines,plan_proposals,"
            "project_budget_revisions,project_heads,project_revisions,projects,"
            "story_bible_heads,story_bible_revisions,story_bibles,story_control_revisions,story_memory_revisions,"
            "volume_heads,volume_revisions,volumes,writing_job_budgets,writing_job_runs,writing_job_scene_marks,writing_jobs,writing_references,writing_rule_versions"
        ),
    ]
    assert not database_path.exists()


def test_records_have_only_the_authorized_columns_and_no_relationships() -> None:
    assert set(ProjectRecord.__table__.columns.keys()) == {
        "id",
        "concurrency_version",
        "created_at",
        "updated_at",
    }
    assert set(ProjectRevisionRecord.__table__.columns.keys()) == {
        "id",
        "project_id",
        "revision_number",
        "title",
        "description",
        "created_at",
    }
    assert set(ProjectHeadRecord.__table__.columns.keys()) == {
        "project_id",
        "revision_id",
        "updated_at",
    }
    assert not inspect(ProjectRecord).relationships
    assert not inspect(ProjectRevisionRecord).relationships
    assert not inspect(ProjectHeadRecord).relationships
    assert all(
        column.default is None and column.server_default is None and column.onupdate is None
        for table in Base.metadata.tables.values()
        for column in table.columns
    )


def test_aggregate_maps_to_three_transient_records_and_back() -> None:
    aggregate = _aggregate()

    project_record, head_record, revision_record = project_aggregate_to_records(aggregate)
    restored = project_aggregate_from_records(project_record, head_record, revision_record)

    assert type(project_record) is ProjectRecord
    assert type(head_record) is ProjectHeadRecord
    assert type(revision_record) is ProjectRevisionRecord
    assert type(project_record.id) is ProjectId
    assert type(project_record.concurrency_version) is ConcurrencyVersion
    assert type(revision_record.id) is ProjectRevisionId
    assert type(revision_record.project_id) is ProjectId
    assert type(revision_record.revision_number) is RevisionNumber
    assert type(head_record.project_id) is ProjectId
    assert type(head_record.revision_id) is ProjectRevisionId
    assert restored == aggregate
    assert type(restored.project) is Project
    assert type(restored.head) is ProjectHead
    assert type(restored.current_revision) is ProjectRevision
    assert type(restored.current_revision.title) is ProjectTitle
    assert type(restored.current_revision.description) is ProjectDescription
    assert restored.project.created_at.tzinfo is UTC
    assert restored.head.updated_at.tzinfo is UTC


def test_individual_record_mappers_restore_domain_values_without_session() -> None:
    aggregate = _aggregate()
    project_record, head_record, revision_record = project_aggregate_to_records(aggregate)

    project = project_from_record(project_record)
    head = project_head_from_record(head_record)
    revision = project_revision_from_record(revision_record)

    assert project == aggregate.project
    assert head == aggregate.head
    assert revision == aggregate.current_revision
    assert inspect(project_record).session is None
    assert inspect(head_record).session is None
    assert inspect(revision_record).session is None


def test_aggregate_mapper_rejects_head_or_revision_from_another_project() -> None:
    aggregate = _aggregate()
    project_record, head_record, revision_record = project_aggregate_to_records(aggregate)
    head_record.project_id = _project_id(90)
    with pytest.raises(InvalidProjectState):
        project_aggregate_from_records(project_record, head_record, revision_record)

    project_record, head_record, revision_record = project_aggregate_to_records(aggregate)
    revision_record.project_id = _project_id(91)
    with pytest.raises(InvalidProjectState):
        project_aggregate_from_records(project_record, head_record, revision_record)


def test_individual_mappers_reject_wrong_record_types() -> None:
    with pytest.raises(InvalidProjectState):
        project_from_record(ProjectRevisionRecord())
    with pytest.raises(InvalidProjectState):
        project_head_from_record(ProjectRecord())
    with pytest.raises(InvalidProjectState):
        project_revision_from_record(ProjectHeadRecord())


def test_domain_to_record_mappers_reject_crossed_domain_objects() -> None:
    aggregate = _aggregate()
    with pytest.raises(InvalidProjectState):
        project_to_record(aggregate.head)
    with pytest.raises(InvalidProjectState):
        project_head_to_record(aggregate.current_revision)
    with pytest.raises(InvalidProjectState):
        project_revision_to_record(aggregate.project)
    with pytest.raises(InvalidProjectState):
        project_aggregate_to_records(aggregate.project)
