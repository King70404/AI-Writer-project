"""Explicit Story Bible record mapper tests."""

from datetime import UTC

import pytest
from sqlalchemy import inspect
from tests.backend.story_bible_repository_support import story_bible_aggregate

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.entities import (
    StoryBible,
    StoryBibleHead,
    StoryBibleRevision,
)
from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleState,
    StoryBibleDataCorruption,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.persistence.mappers import (
    story_bible_aggregate_from_records,
    story_bible_aggregate_to_records,
    story_bible_from_record,
    story_bible_head_from_record,
    story_bible_head_to_record,
    story_bible_revision_from_record,
    story_bible_revision_to_record,
    story_bible_to_record,
)
from aiwebnovel.story_bible.persistence.models import (
    StoryBibleHeadRecord,
    StoryBibleRecord,
    StoryBibleRevisionRecord,
)
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle


def test_aggregate_maps_to_three_transient_records_and_back() -> None:
    aggregate = story_bible_aggregate(
        title="  Canon title  ",
        content="first\r\ncomplete snapshot",
    )

    stable, head, revision = story_bible_aggregate_to_records(aggregate)
    restored = story_bible_aggregate_from_records(stable, head, revision)

    assert type(stable) is StoryBibleRecord
    assert type(head) is StoryBibleHeadRecord
    assert type(revision) is StoryBibleRevisionRecord
    assert type(stable.id) is StoryBibleId
    assert type(stable.project_id) is ProjectId
    assert type(stable.concurrency_version) is ConcurrencyVersion
    assert type(revision.id) is StoryBibleRevisionId
    assert type(revision.revision_number) is RevisionNumber
    assert restored == aggregate
    assert type(restored.story_bible) is StoryBible
    assert type(restored.head) is StoryBibleHead
    assert type(restored.current_revision) is StoryBibleRevision
    assert type(restored.current_revision.title) is StoryBibleTitle
    assert type(restored.current_revision.content) is StoryBibleContent
    assert restored.story_bible.created_at.tzinfo is UTC
    assert restored.head.updated_at.tzinfo is UTC
    assert inspect(stable).session is None
    assert inspect(head).session is None
    assert inspect(revision).session is None


def test_individual_record_mappers_restore_domain_values() -> None:
    aggregate = story_bible_aggregate()
    stable, head, revision = story_bible_aggregate_to_records(aggregate)

    assert story_bible_from_record(stable) == aggregate.story_bible
    assert story_bible_head_from_record(head) == aggregate.head
    assert story_bible_revision_from_record(revision) == aggregate.current_revision


def test_aggregate_mapper_rejects_cross_owned_head_and_revision() -> None:
    aggregate = story_bible_aggregate()
    stable, head, revision = story_bible_aggregate_to_records(aggregate)
    head.story_bible_id = StoryBibleId.new()
    with pytest.raises(StoryBibleDataCorruption):
        story_bible_aggregate_from_records(stable, head, revision)

    stable, head, revision = story_bible_aggregate_to_records(aggregate)
    revision.story_bible_id = StoryBibleId.new()
    with pytest.raises(StoryBibleDataCorruption):
        story_bible_aggregate_from_records(stable, head, revision)


def test_record_to_domain_mappers_reject_wrong_or_invalid_records() -> None:
    with pytest.raises(StoryBibleDataCorruption):
        story_bible_from_record(StoryBibleRevisionRecord())  # type: ignore[arg-type]
    with pytest.raises(StoryBibleDataCorruption):
        story_bible_head_from_record(StoryBibleRecord())  # type: ignore[arg-type]
    with pytest.raises(StoryBibleDataCorruption):
        story_bible_revision_from_record(StoryBibleHeadRecord())  # type: ignore[arg-type]

    aggregate = story_bible_aggregate()
    stable, head, revision = story_bible_aggregate_to_records(aggregate)
    stable.concurrency_version = 0  # type: ignore[assignment]
    head.updated_at = "not-a-time"  # type: ignore[assignment]
    revision.title = ""
    for mapper, record in (
        (story_bible_from_record, stable),
        (story_bible_head_from_record, head),
        (story_bible_revision_from_record, revision),
    ):
        with pytest.raises(StoryBibleDataCorruption):
            mapper(record)  # type: ignore[arg-type]

    stable, _, _ = story_bible_aggregate_to_records(aggregate)
    stable.id = "invalid-story-bible-id"  # type: ignore[assignment]
    with pytest.raises(StoryBibleDataCorruption):
        story_bible_from_record(stable)


def test_domain_to_record_mappers_reject_crossed_objects() -> None:
    aggregate = story_bible_aggregate()
    with pytest.raises(InvalidStoryBibleState):
        story_bible_to_record(aggregate.head)  # type: ignore[arg-type]
    with pytest.raises(InvalidStoryBibleState):
        story_bible_head_to_record(aggregate.current_revision)  # type: ignore[arg-type]
    with pytest.raises(InvalidStoryBibleState):
        story_bible_revision_to_record(aggregate.story_bible)  # type: ignore[arg-type]
    with pytest.raises(InvalidStoryBibleState):
        story_bible_aggregate_to_records(aggregate.story_bible)  # type: ignore[arg-type]
