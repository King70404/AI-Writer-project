"""Explicit mappings between Story Bible domain values and records."""

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.story_bible.entities import (
    StoryBible,
    StoryBibleAggregate,
    StoryBibleHead,
    StoryBibleRevision,
)
from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleState,
    StoryBibleDataCorruption,
)
from aiwebnovel.story_bible.persistence.models import (
    StoryBibleHeadRecord,
    StoryBibleRecord,
    StoryBibleRevisionRecord,
)
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle


def story_bible_to_record(story_bible: StoryBible) -> StoryBibleRecord:
    """Copy one validated stable object into a transient record."""
    if type(story_bible) is not StoryBible:
        raise InvalidStoryBibleState
    return StoryBibleRecord(
        id=story_bible.id,
        project_id=story_bible.project_id,
        concurrency_version=story_bible.concurrency_version,
        created_at=story_bible.created_at,
        updated_at=story_bible.updated_at,
    )


def story_bible_revision_to_record(
    revision: StoryBibleRevision,
) -> StoryBibleRevisionRecord:
    """Copy one immutable complete snapshot into a transient record."""
    if type(revision) is not StoryBibleRevision:
        raise InvalidStoryBibleState
    return StoryBibleRevisionRecord(
        id=revision.id,
        story_bible_id=revision.story_bible_id,
        revision_number=revision.revision_number,
        title=str(revision.title),
        content=str(revision.content),
        created_at=revision.created_at,
    )


def story_bible_head_to_record(head: StoryBibleHead) -> StoryBibleHeadRecord:
    """Copy one current pointer into a transient record."""
    if type(head) is not StoryBibleHead:
        raise InvalidStoryBibleState
    return StoryBibleHeadRecord(
        story_bible_id=head.story_bible_id,
        revision_id=head.revision_id,
        updated_at=head.updated_at,
    )


def story_bible_from_record(record: StoryBibleRecord) -> StoryBible:
    """Restore one stable object and reject invalid stored values."""
    if type(record) is not StoryBibleRecord:
        raise StoryBibleDataCorruption
    try:
        return StoryBible(
            id=record.id,
            project_id=record.project_id,
            concurrency_version=record.concurrency_version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
    except (DomainError, TypeError, ValueError) as exc:
        raise StoryBibleDataCorruption from exc


def story_bible_revision_from_record(
    record: StoryBibleRevisionRecord,
) -> StoryBibleRevision:
    """Restore one revision and reapply all text and identity rules."""
    if type(record) is not StoryBibleRevisionRecord:
        raise StoryBibleDataCorruption
    try:
        return StoryBibleRevision(
            id=record.id,
            story_bible_id=record.story_bible_id,
            revision_number=record.revision_number,
            title=StoryBibleTitle(record.title),
            content=StoryBibleContent(record.content),
            created_at=record.created_at,
        )
    except (DomainError, TypeError, ValueError) as exc:
        raise StoryBibleDataCorruption from exc


def story_bible_head_from_record(record: StoryBibleHeadRecord) -> StoryBibleHead:
    """Restore one current pointer and reject invalid stored values."""
    if type(record) is not StoryBibleHeadRecord:
        raise StoryBibleDataCorruption
    try:
        return StoryBibleHead(
            story_bible_id=record.story_bible_id,
            revision_id=record.revision_id,
            updated_at=record.updated_at,
        )
    except (DomainError, TypeError, ValueError) as exc:
        raise StoryBibleDataCorruption from exc


def story_bible_aggregate_to_records(
    aggregate: StoryBibleAggregate,
) -> tuple[StoryBibleRecord, StoryBibleHeadRecord, StoryBibleRevisionRecord]:
    """Map one consistent aggregate to three transient records."""
    if type(aggregate) is not StoryBibleAggregate:
        raise InvalidStoryBibleState
    return (
        story_bible_to_record(aggregate.story_bible),
        story_bible_head_to_record(aggregate.head),
        story_bible_revision_to_record(aggregate.current_revision),
    )


def story_bible_aggregate_from_records(
    story_bible_record: StoryBibleRecord,
    head_record: StoryBibleHeadRecord,
    revision_record: StoryBibleRevisionRecord,
) -> StoryBibleAggregate:
    """Restore a fully validated current aggregate without database access."""
    try:
        return StoryBibleAggregate(
            story_bible=story_bible_from_record(story_bible_record),
            head=story_bible_head_from_record(head_record),
            current_revision=story_bible_revision_from_record(revision_record),
        )
    except StoryBibleDataCorruption:
        raise
    except (DomainError, TypeError, ValueError) as exc:
        raise StoryBibleDataCorruption from exc


__all__ = [
    "story_bible_aggregate_from_records",
    "story_bible_aggregate_to_records",
    "story_bible_from_record",
    "story_bible_head_from_record",
    "story_bible_head_to_record",
    "story_bible_revision_from_record",
    "story_bible_revision_to_record",
    "story_bible_to_record",
]
