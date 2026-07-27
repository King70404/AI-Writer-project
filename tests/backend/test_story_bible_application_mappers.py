"""Pure explicit Story Bible aggregate-to-snapshot mapping."""

from dataclasses import replace

import pytest
from tests.backend.story_bible_support import initial_aggregate

from aiwebnovel.story_bible.application.mappers import (
    story_bible_snapshot_from_aggregate,
)
from aiwebnovel.story_bible.application.models import StoryBibleSnapshot
from aiwebnovel.story_bible.errors import InvalidStoryBibleState


def test_mapper_explicitly_detaches_every_current_aggregate_field() -> None:
    aggregate = initial_aggregate(title="  世界规则  ", content="a\r\nb")
    before = aggregate

    snapshot = story_bible_snapshot_from_aggregate(aggregate)

    assert type(snapshot) is StoryBibleSnapshot
    assert snapshot.story_bible_id == str(aggregate.story_bible.id)
    assert snapshot.project_id == str(aggregate.story_bible.project_id)
    assert snapshot.current_revision_id == str(aggregate.current_revision.id)
    assert snapshot.revision_number == int(aggregate.current_revision.revision_number)
    assert snapshot.concurrency_version == int(aggregate.story_bible.concurrency_version)
    assert snapshot.title == "世界规则"
    assert snapshot.content == "a\nb"
    assert snapshot.created_at == aggregate.story_bible.created_at
    assert snapshot.updated_at == aggregate.story_bible.updated_at
    assert snapshot.revision_created_at == aggregate.current_revision.created_at
    assert snapshot.head_updated_at == aggregate.head.updated_at
    assert aggregate is before


def test_mapper_rejects_non_aggregate_without_echoing_object_details() -> None:
    hostile = object()

    with pytest.raises(InvalidStoryBibleState) as captured:
        story_bible_snapshot_from_aggregate(hostile)  # type: ignore[arg-type]

    assert "object" not in str(captured.value).lower()


def test_snapshot_is_independent_from_any_later_aggregate_reference() -> None:
    aggregate = initial_aggregate()
    snapshot = story_bible_snapshot_from_aggregate(aggregate)
    discarded = replace(aggregate, current_revision=aggregate.current_revision)

    del aggregate

    assert snapshot.title == "都市异能设定"
    assert discarded is not snapshot
