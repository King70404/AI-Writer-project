"""Story Bible record shape and deterministic metadata registration tests."""

from sqlalchemy import inspect

from aiwebnovel.db.base import Base
from aiwebnovel.db.model_registry import (
    AI_WORKFLOW_TABLE_NAMES,
    BUSINESS_TABLE_NAMES,
    CANDIDATE_BUDGET_TABLE_NAMES,
    CHARACTER_TABLE_NAMES,
    IMPORT_TABLE_NAMES,
    NOVEL_STRUCTURE_TABLE_NAMES,
    STORY_BIBLE_TABLE_NAMES,
    STORY_CONTROL_TABLE_NAMES,
    STORY_MEMORY_TABLE_NAMES,
    USAGE_TABLE_NAMES,
    WORKBENCH_TABLE_NAMES,
    WRITING_STUDIO_TABLE_NAMES,
    load_model_metadata,
)
from aiwebnovel.story_bible.persistence.models import (
    StoryBibleHeadRecord,
    StoryBibleRecord,
    StoryBibleRevisionRecord,
)


def test_registry_contains_exactly_authorized_business_tables() -> None:
    metadata = load_model_metadata()

    assert metadata is Base.metadata
    assert frozenset(metadata.tables) == BUSINESS_TABLE_NAMES
    assert (
        frozenset({"story_bibles", "story_bible_revisions", "story_bible_heads"})
        == STORY_BIBLE_TABLE_NAMES
    )
    assert (
        frozenset({"characters", "character_revisions", "character_heads"}) == CHARACTER_TABLE_NAMES
    )
    assert len(NOVEL_STRUCTURE_TABLE_NAMES) == 9
    assert set(metadata.tables) == {
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
    }
    assert "alembic_version" not in metadata.tables


def test_records_have_only_authorized_columns_and_no_relationships() -> None:
    assert set(StoryBibleRecord.__table__.columns.keys()) == {
        "id",
        "project_id",
        "concurrency_version",
        "created_at",
        "updated_at",
    }
    assert set(StoryBibleRevisionRecord.__table__.columns.keys()) == {
        "id",
        "story_bible_id",
        "revision_number",
        "title",
        "content",
        "created_at",
    }
    assert set(StoryBibleHeadRecord.__table__.columns.keys()) == {
        "story_bible_id",
        "revision_id",
        "updated_at",
    }
    assert not inspect(StoryBibleRecord).relationships
    assert not inspect(StoryBibleRevisionRecord).relationships
    assert not inspect(StoryBibleHeadRecord).relationships
    assert all(
        column.default is None and column.server_default is None and column.onupdate is None
        for table_name in STORY_BIBLE_TABLE_NAMES
        for column in Base.metadata.tables[table_name].columns
    )


def test_revision_repr_never_contains_user_text() -> None:
    record = StoryBibleRevisionRecord(title="private title", content="private content")

    assert repr(record) == "<StoryBibleRevisionRecord>"
    assert "private" not in repr(record)
