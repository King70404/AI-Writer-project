"""Deterministic SQLAlchemy statements for Story Bible persistence."""

from datetime import datetime

from sqlalchemy import Select, Update, and_, select, update

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import ProjectRecord
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.persistence.models import (
    StoryBibleHeadRecord,
    StoryBibleRecord,
    StoryBibleRevisionRecord,
)


def project_exists_query(project_id: ProjectId) -> Select[tuple[ProjectId]]:
    """Select only the Project ownership identity needed by this module."""
    return select(ProjectRecord.id).where(ProjectRecord.id == project_id)


def story_bible_identity_query(
    story_bible_id: StoryBibleId,
) -> Select[tuple[StoryBibleId]]:
    """Select a stable Story Bible identity without loading content."""
    return select(StoryBibleRecord.id).where(StoryBibleRecord.id == story_bible_id)


def story_bible_for_project_identity_query(
    project_id: ProjectId,
) -> Select[tuple[StoryBibleId]]:
    """Select the unique Story Bible identity owned by one Project."""
    return select(StoryBibleRecord.id).where(StoryBibleRecord.project_id == project_id)


def current_story_bible_query(
    story_bible_id: StoryBibleId,
) -> Select[
    tuple[
        StoryBibleRecord,
        StoryBibleHeadRecord,
        StoryBibleRevisionRecord,
    ]
]:
    """Select one stable object, explicit head, and current revision."""
    return (
        select(StoryBibleRecord, StoryBibleHeadRecord, StoryBibleRevisionRecord)
        .outerjoin(
            StoryBibleHeadRecord,
            StoryBibleHeadRecord.story_bible_id == StoryBibleRecord.id,
        )
        .outerjoin(
            StoryBibleRevisionRecord,
            and_(
                StoryBibleRevisionRecord.story_bible_id == StoryBibleHeadRecord.story_bible_id,
                StoryBibleRevisionRecord.id == StoryBibleHeadRecord.revision_id,
            ),
        )
        .where(StoryBibleRecord.id == story_bible_id)
    )


def story_bible_for_project_query(
    project_id: ProjectId,
) -> Select[
    tuple[
        ProjectId,
        StoryBibleRecord,
        StoryBibleHeadRecord,
        StoryBibleRevisionRecord,
    ]
]:
    """Select a Project and its optional unique current Story Bible."""
    return (
        select(
            ProjectRecord.id,
            StoryBibleRecord,
            StoryBibleHeadRecord,
            StoryBibleRevisionRecord,
        )
        .outerjoin(
            StoryBibleRecord,
            StoryBibleRecord.project_id == ProjectRecord.id,
        )
        .outerjoin(
            StoryBibleHeadRecord,
            StoryBibleHeadRecord.story_bible_id == StoryBibleRecord.id,
        )
        .outerjoin(
            StoryBibleRevisionRecord,
            and_(
                StoryBibleRevisionRecord.story_bible_id == StoryBibleHeadRecord.story_bible_id,
                StoryBibleRevisionRecord.id == StoryBibleHeadRecord.revision_id,
            ),
        )
        .where(ProjectRecord.id == project_id)
    )


def story_bible_compare_and_swap(
    story_bible_id: StoryBibleId,
    expected_version: ConcurrencyVersion,
    new_version: ConcurrencyVersion,
    updated_at: datetime,
) -> Update:
    """Update only version and time when the stable version still matches."""
    return (
        update(StoryBibleRecord)
        .where(
            StoryBibleRecord.id == story_bible_id,
            StoryBibleRecord.concurrency_version == expected_version,
        )
        .values(concurrency_version=new_version, updated_at=updated_at)
    )


def story_bible_head_compare_and_swap(
    story_bible_id: StoryBibleId,
    expected_revision_id: StoryBibleRevisionId,
    new_revision_id: StoryBibleRevisionId,
    updated_at: datetime,
) -> Update:
    """Move the explicit head only when it targets the expected revision."""
    return (
        update(StoryBibleHeadRecord)
        .where(
            StoryBibleHeadRecord.story_bible_id == story_bible_id,
            StoryBibleHeadRecord.revision_id == expected_revision_id,
        )
        .values(revision_id=new_revision_id, updated_at=updated_at)
    )


__all__ = [
    "current_story_bible_query",
    "project_exists_query",
    "story_bible_compare_and_swap",
    "story_bible_for_project_identity_query",
    "story_bible_for_project_query",
    "story_bible_head_compare_and_swap",
    "story_bible_identity_query",
]
