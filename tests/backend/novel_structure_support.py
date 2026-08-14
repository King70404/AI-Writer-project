"""Deterministic novel-structure domain fixtures."""

from datetime import UTC, datetime

from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.novel_structure import (
    ChapterAggregate,
    ChapterId,
    ChapterRevisionId,
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
    OutlineAggregate,
    OutlineId,
    OutlineRevisionId,
    VolumeAggregate,
    VolumeId,
    VolumeRevisionId,
    create_initial_chapter,
    create_initial_outline,
    create_initial_volume,
)
from aiwebnovel.project.identifiers import ProjectId

BASE_TIME = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def project_id(randomness: int = 1) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_parts(1, randomness))


def outline_id(randomness: int = 2) -> OutlineId:
    return OutlineId.from_ulid(Ulid.from_parts(1, randomness))


def outline_revision_id(randomness: int = 3) -> OutlineRevisionId:
    return OutlineRevisionId.from_ulid(Ulid.from_parts(1, randomness))


def volume_id(randomness: int = 4) -> VolumeId:
    return VolumeId.from_ulid(Ulid.from_parts(1, randomness))


def volume_revision_id(randomness: int = 5) -> VolumeRevisionId:
    return VolumeRevisionId.from_ulid(Ulid.from_parts(1, randomness))


def chapter_id(randomness: int = 6) -> ChapterId:
    return ChapterId.from_ulid(Ulid.from_parts(1, randomness))


def chapter_revision_id(randomness: int = 7) -> ChapterRevisionId:
    return ChapterRevisionId.from_ulid(Ulid.from_parts(1, randomness))


def initial_outline() -> OutlineAggregate:
    return create_initial_outline(
        outline_id=outline_id(),
        revision_id=outline_revision_id(),
        project_id=project_id(),
        title=NovelStructureTitle("总纲"),
        summary=NovelStructureSummary("全书规划"),
        now=BASE_TIME,
    )


def initial_volume() -> VolumeAggregate:
    return create_initial_volume(
        volume_id=volume_id(),
        revision_id=volume_revision_id(),
        project_id=project_id(),
        title=NovelStructureTitle("第一卷"),
        summary=NovelStructureSummary("卷规划"),
        position=NovelStructurePosition(1),
        now=BASE_TIME,
    )


def initial_chapter() -> ChapterAggregate:
    volume = initial_volume().volume
    return create_initial_chapter(
        chapter_id=chapter_id(),
        revision_id=chapter_revision_id(),
        project_id=volume.project_id,
        volume=volume,
        title=NovelStructureTitle("第一章"),
        summary=NovelStructureSummary("章节规划"),
        position=NovelStructurePosition(1),
        now=BASE_TIME,
    )
