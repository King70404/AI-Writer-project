"""Explicit novel-structure persistence mapper contracts."""

from collections.abc import Callable

import pytest
from tests.backend.novel_structure_repository_support import (
    chapter_aggregate,
    outline_aggregate,
    volume_aggregate,
)

from aiwebnovel.novel_structure import (
    InvalidNovelStructureState,
    NovelStructureDataCorruption,
)
from aiwebnovel.novel_structure.persistence.mappers import (
    chapter_aggregate_from_records,
    chapter_aggregate_to_records,
    chapter_revision_to_record,
    outline_aggregate_from_records,
    outline_aggregate_to_records,
    outline_revision_to_record,
    volume_aggregate_from_records,
    volume_aggregate_to_records,
    volume_revision_to_record,
)


@pytest.mark.parametrize(
    "mapper",
    [
        outline_aggregate_to_records,
        outline_revision_to_record,
        volume_aggregate_to_records,
        volume_revision_to_record,
        chapter_aggregate_to_records,
        chapter_revision_to_record,
    ],
)
def test_record_mappers_reject_non_domain_values(mapper: Callable[..., object]) -> None:
    with pytest.raises(InvalidNovelStructureState):
        mapper(object())


def test_outline_records_round_trip_and_hide_revision_content_in_repr() -> None:
    aggregate = outline_aggregate()
    stable, head, revision = outline_aggregate_to_records(aggregate)

    assert outline_aggregate_from_records(stable, head, revision) == aggregate
    assert repr(revision) == "<OutlineRevisionRecord>"

    revision.title = "\x00"
    with pytest.raises(NovelStructureDataCorruption):
        outline_aggregate_from_records(stable, head, revision)


def test_volume_records_round_trip_and_validate_current_position() -> None:
    aggregate = volume_aggregate()
    stable, head, revision = volume_aggregate_to_records(aggregate)

    assert volume_aggregate_from_records(stable, head, revision) == aggregate
    assert repr(revision) == "<VolumeRevisionRecord>"

    stable.current_position = 2
    with pytest.raises(NovelStructureDataCorruption):
        volume_aggregate_from_records(stable, head, revision)
    stable.current_position = 1
    revision.summary = "\x00"
    with pytest.raises(NovelStructureDataCorruption):
        volume_aggregate_from_records(stable, head, revision)


def test_chapter_records_round_trip_and_validate_current_position() -> None:
    volume = volume_aggregate()
    aggregate = chapter_aggregate(volume)
    stable, head, revision = chapter_aggregate_to_records(aggregate)

    assert chapter_aggregate_from_records(stable, head, revision) == aggregate
    assert repr(revision) == "<ChapterRevisionRecord>"

    stable.current_position = 2
    with pytest.raises(NovelStructureDataCorruption):
        chapter_aggregate_from_records(stable, head, revision)
    stable.current_position = 1
    revision.title = "\x00"
    with pytest.raises(NovelStructureDataCorruption):
        chapter_aggregate_from_records(stable, head, revision)


@pytest.mark.parametrize(
    "mapper",
    [
        outline_aggregate_from_records,
        volume_aggregate_from_records,
        chapter_aggregate_from_records,
    ],
)
def test_record_to_aggregate_mappers_reject_wrong_record_types(
    mapper: Callable[..., object],
) -> None:
    with pytest.raises(NovelStructureDataCorruption):
        mapper(object(), object(), object())
