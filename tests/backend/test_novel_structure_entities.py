"""Entity invariants for Outline, Volume, and Chapter aggregates."""

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone

import pytest
from tests.backend.novel_structure_support import (
    BASE_TIME,
    chapter_id,
    chapter_revision_id,
    initial_chapter,
    initial_outline,
    initial_volume,
    outline_id,
    outline_revision_id,
    project_id,
    volume_id,
    volume_revision_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.novel_structure import (
    Chapter,
    ChapterHead,
    ChapterRevision,
    InvalidNovelStructureState,
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
    Outline,
    OutlineAggregate,
    OutlineHead,
    OutlineRevision,
    Volume,
    VolumeAggregate,
    VolumeHead,
    VolumeRevision,
    assert_chapter_belongs_to_volume,
)


def test_legal_aggregates_have_stable_revision_and_head_fields() -> None:
    outline = initial_outline()
    volume = initial_volume()
    chapter = initial_chapter()

    assert outline.outline.project_id == project_id()
    assert outline.current_revision.outline_id == outline.outline.id
    assert outline.head.revision_id == outline.current_revision.id
    assert volume.volume.project_id == project_id()
    assert volume.current_revision.volume_id == volume.volume.id
    assert volume.head.revision_id == volume.current_revision.id
    assert chapter.chapter.project_id == volume.volume.project_id
    assert chapter.chapter.volume_id == volume.volume.id
    assert chapter.current_revision.chapter_id == chapter.chapter.id
    assert chapter.head.revision_id == chapter.current_revision.id
    for aggregate in (outline, volume, chapter):
        stable = (
            aggregate.outline
            if isinstance(aggregate, OutlineAggregate)
            else (aggregate.volume if isinstance(aggregate, VolumeAggregate) else aggregate.chapter)
        )
        assert stable.concurrency_version == ConcurrencyVersion(1)
        assert aggregate.current_revision.revision_number == RevisionNumber(1)


def test_entities_normalize_aware_times_to_utc() -> None:
    local_time = BASE_TIME.astimezone(timezone(timedelta(hours=8)))

    outline = Outline(outline_id(), project_id(), ConcurrencyVersion(), local_time, local_time)
    revision = OutlineRevision(
        outline_revision_id(),
        outline.id,
        RevisionNumber(),
        NovelStructureTitle("总纲"),
        NovelStructureSummary(),
        local_time,
    )
    head = OutlineHead(outline.id, revision.id, local_time)

    assert outline.created_at == BASE_TIME
    assert outline.updated_at == BASE_TIME
    assert revision.created_at == BASE_TIME
    assert head.updated_at == BASE_TIME


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Outline(volume_id(), project_id(), ConcurrencyVersion(), BASE_TIME, BASE_TIME),
        lambda: Outline(outline_id(), outline_id(), ConcurrencyVersion(), BASE_TIME, BASE_TIME),
        lambda: Outline(outline_id(), project_id(), True, BASE_TIME, BASE_TIME),
        lambda: Outline(outline_id(), project_id(), ConcurrencyVersion(), object(), BASE_TIME),
        lambda: Outline(
            outline_id(),
            project_id(),
            ConcurrencyVersion(),
            BASE_TIME,
            BASE_TIME - timedelta(seconds=1),
        ),
        lambda: Volume(outline_id(), project_id(), ConcurrencyVersion(), BASE_TIME, BASE_TIME),
        lambda: Volume(volume_id(), volume_id(), ConcurrencyVersion(), BASE_TIME, BASE_TIME),
        lambda: Volume(volume_id(), project_id(), True, BASE_TIME, BASE_TIME),
        lambda: Volume(
            volume_id(),
            project_id(),
            ConcurrencyVersion(),
            BASE_TIME,
            BASE_TIME - timedelta(seconds=1),
        ),
        lambda: Chapter(
            volume_id(),
            project_id(),
            volume_id(),
            ConcurrencyVersion(),
            BASE_TIME,
            BASE_TIME,
        ),
        lambda: Chapter(
            chapter_id(),
            volume_id(),
            volume_id(),
            ConcurrencyVersion(),
            BASE_TIME,
            BASE_TIME,
        ),
        lambda: Chapter(
            chapter_id(),
            project_id(),
            chapter_id(),
            ConcurrencyVersion(),
            BASE_TIME,
            BASE_TIME,
        ),
        lambda: Chapter(chapter_id(), project_id(), volume_id(), True, BASE_TIME, BASE_TIME),
        lambda: Chapter(
            chapter_id(),
            project_id(),
            volume_id(),
            ConcurrencyVersion(),
            BASE_TIME,
            BASE_TIME - timedelta(seconds=1),
        ),
    ],
)
def test_stable_entities_reject_wrong_nominal_types_and_times(factory: object) -> None:
    with pytest.raises(InvalidNovelStructureState):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: OutlineRevision(
            volume_revision_id(),
            outline_id(),
            RevisionNumber(),
            NovelStructureTitle("总纲"),
            NovelStructureSummary(),
            BASE_TIME,
        ),
        lambda: OutlineRevision(
            outline_revision_id(),
            volume_id(),
            RevisionNumber(),
            NovelStructureTitle("总纲"),
            NovelStructureSummary(),
            BASE_TIME,
        ),
        lambda: OutlineRevision(
            outline_revision_id(),
            outline_id(),
            ConcurrencyVersion(),
            NovelStructureTitle("总纲"),
            NovelStructureSummary(),
            BASE_TIME,
        ),
        lambda: VolumeRevision(
            volume_revision_id(),
            volume_id(),
            RevisionNumber(),
            NovelStructureSummary(),
            NovelStructureSummary(),
            NovelStructurePosition(1),
            BASE_TIME,
        ),
        lambda: VolumeRevision(
            volume_revision_id(),
            volume_id(),
            RevisionNumber(),
            NovelStructureTitle("卷"),
            NovelStructureSummary(),
            True,
            BASE_TIME,
        ),
        lambda: ChapterRevision(
            volume_revision_id(),
            chapter_id(),
            RevisionNumber(),
            NovelStructureTitle("章"),
            NovelStructureSummary(),
            NovelStructurePosition(1),
            BASE_TIME,
        ),
        lambda: ChapterRevision(
            chapter_revision_id(),
            chapter_id(),
            RevisionNumber(),
            NovelStructureTitle("章"),
            NovelStructureTitle("wrong"),
            NovelStructurePosition(1),
            BASE_TIME,
        ),
        lambda: replace(initial_chapter().current_revision, created_at=object()),
    ],
)
def test_revision_entities_reject_wrong_nominal_types(factory: object) -> None:
    with pytest.raises(InvalidNovelStructureState):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: OutlineHead(volume_id(), outline_revision_id(), BASE_TIME),
        lambda: OutlineHead(outline_id(), volume_revision_id(), BASE_TIME),
        lambda: VolumeHead(outline_id(), volume_revision_id(), BASE_TIME),
        lambda: VolumeHead(volume_id(), outline_revision_id(), BASE_TIME),
        lambda: ChapterHead(volume_id(), chapter_revision_id(), BASE_TIME),
        lambda: ChapterHead(chapter_id(), volume_revision_id(), BASE_TIME),
        lambda: replace(initial_outline().head, updated_at=object()),
    ],
)
def test_heads_reject_wrong_ids_or_time(factory: object) -> None:
    with pytest.raises(InvalidNovelStructureState):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(initial_outline(), outline=initial_volume().volume),
        lambda: replace(initial_outline(), head=initial_volume().head),
        lambda: replace(initial_outline(), current_revision=initial_volume().current_revision),
        lambda: replace(
            initial_outline(),
            head=replace(initial_outline().head, outline_id=outline_id(30)),
        ),
        lambda: replace(
            initial_outline(),
            current_revision=replace(initial_outline().current_revision, outline_id=outline_id(30)),
        ),
        lambda: replace(
            initial_outline(),
            head=replace(initial_outline().head, revision_id=outline_revision_id(30)),
        ),
        lambda: replace(
            initial_outline(),
            outline=replace(initial_outline().outline, concurrency_version=ConcurrencyVersion(2)),
        ),
        lambda: replace(
            initial_outline(),
            head=replace(initial_outline().head, updated_at=BASE_TIME + timedelta(seconds=1)),
        ),
        lambda: replace(initial_volume(), volume=initial_outline().outline),
        lambda: replace(initial_volume(), head=initial_outline().head),
        lambda: replace(initial_volume(), current_revision=initial_outline().current_revision),
        lambda: replace(initial_chapter(), chapter=initial_outline().outline),
        lambda: replace(initial_chapter(), head=initial_outline().head),
        lambda: replace(initial_chapter(), current_revision=initial_outline().current_revision),
    ],
)
def test_aggregates_reject_inconsistent_components(factory: object) -> None:
    with pytest.raises(InvalidNovelStructureState):
        factory()  # type: ignore[operator]


def test_chapter_volume_ownership_requires_same_volume_and_project() -> None:
    chapter = initial_chapter().chapter
    volume = initial_volume().volume

    assert_chapter_belongs_to_volume(chapter, volume)
    with pytest.raises(InvalidNovelStructureState):
        assert_chapter_belongs_to_volume(chapter, replace(volume, id=volume_id(30)))
    with pytest.raises(InvalidNovelStructureState):
        assert_chapter_belongs_to_volume(chapter, replace(volume, project_id=project_id(30)))
    with pytest.raises(InvalidNovelStructureState):
        assert_chapter_belongs_to_volume(object(), volume)  # type: ignore[arg-type]
    with pytest.raises(InvalidNovelStructureState):
        assert_chapter_belongs_to_volume(chapter, object())  # type: ignore[arg-type]


def test_all_entities_and_revisions_are_frozen_slots_objects() -> None:
    aggregates = (initial_outline(), initial_volume(), initial_chapter())
    values = [
        item
        for aggregate in aggregates
        for item in (
            aggregate,
            aggregate.outline
            if isinstance(aggregate, OutlineAggregate)
            else (
                aggregate.volume if isinstance(aggregate, VolumeAggregate) else aggregate.chapter
            ),
            aggregate.head,
            aggregate.current_revision,
        )
    ]

    assert all(not hasattr(value, "__dict__") for value in values)
    for value in values:
        with pytest.raises((FrozenInstanceError, AttributeError)):
            setattr(value, value.__slots__[0], object())
