"""Explicit aggregate-to-snapshot mapping for novel structure."""

from aiwebnovel.novel_structure.application.models import (
    ChapterSnapshot,
    OutlineSnapshot,
    VolumeSnapshot,
)
from aiwebnovel.novel_structure.entities import (
    ChapterAggregate,
    OutlineAggregate,
    VolumeAggregate,
)
from aiwebnovel.novel_structure.errors import InvalidNovelStructureState


def outline_snapshot_from_aggregate(aggregate: OutlineAggregate) -> OutlineSnapshot:
    if type(aggregate) is not OutlineAggregate:
        raise InvalidNovelStructureState
    return OutlineSnapshot(
        outline_id=str(aggregate.outline.id),
        project_id=str(aggregate.outline.project_id),
        current_revision_id=str(aggregate.current_revision.id),
        revision_number=int(aggregate.current_revision.revision_number),
        concurrency_version=int(aggregate.outline.concurrency_version),
        title=str(aggregate.current_revision.title),
        summary=str(aggregate.current_revision.summary),
        created_at=aggregate.outline.created_at,
        updated_at=aggregate.outline.updated_at,
        revision_created_at=aggregate.current_revision.created_at,
    )


def volume_snapshot_from_aggregate(aggregate: VolumeAggregate) -> VolumeSnapshot:
    if type(aggregate) is not VolumeAggregate:
        raise InvalidNovelStructureState
    return VolumeSnapshot(
        volume_id=str(aggregate.volume.id),
        project_id=str(aggregate.volume.project_id),
        current_revision_id=str(aggregate.current_revision.id),
        revision_number=int(aggregate.current_revision.revision_number),
        concurrency_version=int(aggregate.volume.concurrency_version),
        title=str(aggregate.current_revision.title),
        summary=str(aggregate.current_revision.summary),
        position=int(aggregate.current_revision.position),
        created_at=aggregate.volume.created_at,
        updated_at=aggregate.volume.updated_at,
        revision_created_at=aggregate.current_revision.created_at,
    )


def chapter_snapshot_from_aggregate(aggregate: ChapterAggregate) -> ChapterSnapshot:
    if type(aggregate) is not ChapterAggregate:
        raise InvalidNovelStructureState
    return ChapterSnapshot(
        chapter_id=str(aggregate.chapter.id),
        project_id=str(aggregate.chapter.project_id),
        volume_id=str(aggregate.chapter.volume_id),
        current_revision_id=str(aggregate.current_revision.id),
        revision_number=int(aggregate.current_revision.revision_number),
        concurrency_version=int(aggregate.chapter.concurrency_version),
        title=str(aggregate.current_revision.title),
        summary=str(aggregate.current_revision.summary),
        position=int(aggregate.current_revision.position),
        created_at=aggregate.chapter.created_at,
        updated_at=aggregate.chapter.updated_at,
        revision_created_at=aggregate.current_revision.created_at,
    )


__all__ = [
    "chapter_snapshot_from_aggregate",
    "outline_snapshot_from_aggregate",
    "volume_snapshot_from_aggregate",
]
