"""Explicit mappings between novel-structure domain values and records."""

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.entities import (
    Chapter,
    ChapterAggregate,
    ChapterHead,
    ChapterRevision,
    Outline,
    OutlineAggregate,
    OutlineHead,
    OutlineRevision,
    Volume,
    VolumeAggregate,
    VolumeHead,
    VolumeRevision,
)
from aiwebnovel.novel_structure.errors import (
    InvalidNovelStructureState,
    NovelStructureDataCorruption,
)
from aiwebnovel.novel_structure.persistence.models import (
    ChapterHeadRecord,
    ChapterRecord,
    ChapterRevisionRecord,
    OutlineHeadRecord,
    OutlineRecord,
    OutlineRevisionRecord,
    VolumeHeadRecord,
    VolumeRecord,
    VolumeRevisionRecord,
)
from aiwebnovel.novel_structure.values import (
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)


def outline_aggregate_to_records(
    aggregate: OutlineAggregate,
) -> tuple[OutlineRecord, OutlineHeadRecord, OutlineRevisionRecord]:
    if type(aggregate) is not OutlineAggregate:
        raise InvalidNovelStructureState
    return (
        OutlineRecord(
            id=aggregate.outline.id,
            project_id=aggregate.outline.project_id,
            concurrency_version=aggregate.outline.concurrency_version,
            created_at=aggregate.outline.created_at,
            updated_at=aggregate.outline.updated_at,
        ),
        OutlineHeadRecord(
            outline_id=aggregate.head.outline_id,
            revision_id=aggregate.head.revision_id,
            updated_at=aggregate.head.updated_at,
        ),
        outline_revision_to_record(aggregate.current_revision),
    )


def outline_revision_to_record(revision: OutlineRevision) -> OutlineRevisionRecord:
    if type(revision) is not OutlineRevision:
        raise InvalidNovelStructureState
    return OutlineRevisionRecord(
        id=revision.id,
        outline_id=revision.outline_id,
        revision_number=revision.revision_number,
        title=str(revision.title),
        summary=str(revision.summary),
        created_at=revision.created_at,
    )


def outline_aggregate_from_records(
    stable: OutlineRecord,
    head: OutlineHeadRecord,
    revision: OutlineRevisionRecord,
) -> OutlineAggregate:
    if (
        type(stable) is not OutlineRecord
        or type(head) is not OutlineHeadRecord
        or type(revision) is not OutlineRevisionRecord
    ):
        raise NovelStructureDataCorruption
    try:
        return OutlineAggregate(
            outline=Outline(
                id=stable.id,
                project_id=stable.project_id,
                concurrency_version=stable.concurrency_version,
                created_at=stable.created_at,
                updated_at=stable.updated_at,
            ),
            head=OutlineHead(
                outline_id=head.outline_id,
                revision_id=head.revision_id,
                updated_at=head.updated_at,
            ),
            current_revision=OutlineRevision(
                id=revision.id,
                outline_id=revision.outline_id,
                revision_number=revision.revision_number,
                title=NovelStructureTitle(revision.title),
                summary=NovelStructureSummary(revision.summary),
                created_at=revision.created_at,
            ),
        )
    except (DomainError, TypeError, ValueError) as exc:
        raise NovelStructureDataCorruption from exc


def volume_aggregate_to_records(
    aggregate: VolumeAggregate,
) -> tuple[VolumeRecord, VolumeHeadRecord, VolumeRevisionRecord]:
    if type(aggregate) is not VolumeAggregate:
        raise InvalidNovelStructureState
    return (
        VolumeRecord(
            id=aggregate.volume.id,
            project_id=aggregate.volume.project_id,
            current_position=int(aggregate.current_revision.position),
            concurrency_version=aggregate.volume.concurrency_version,
            created_at=aggregate.volume.created_at,
            updated_at=aggregate.volume.updated_at,
        ),
        VolumeHeadRecord(
            volume_id=aggregate.head.volume_id,
            revision_id=aggregate.head.revision_id,
            updated_at=aggregate.head.updated_at,
        ),
        volume_revision_to_record(aggregate.current_revision),
    )


def volume_revision_to_record(revision: VolumeRevision) -> VolumeRevisionRecord:
    if type(revision) is not VolumeRevision:
        raise InvalidNovelStructureState
    return VolumeRevisionRecord(
        id=revision.id,
        volume_id=revision.volume_id,
        revision_number=revision.revision_number,
        title=str(revision.title),
        summary=str(revision.summary),
        position=int(revision.position),
        created_at=revision.created_at,
    )


def volume_aggregate_from_records(
    stable: VolumeRecord,
    head: VolumeHeadRecord,
    revision: VolumeRevisionRecord,
) -> VolumeAggregate:
    if (
        type(stable) is not VolumeRecord
        or type(head) is not VolumeHeadRecord
        or type(revision) is not VolumeRevisionRecord
        or stable.current_position != revision.position
    ):
        raise NovelStructureDataCorruption
    try:
        return VolumeAggregate(
            volume=Volume(
                id=stable.id,
                project_id=stable.project_id,
                concurrency_version=stable.concurrency_version,
                created_at=stable.created_at,
                updated_at=stable.updated_at,
            ),
            head=VolumeHead(
                volume_id=head.volume_id,
                revision_id=head.revision_id,
                updated_at=head.updated_at,
            ),
            current_revision=VolumeRevision(
                id=revision.id,
                volume_id=revision.volume_id,
                revision_number=revision.revision_number,
                title=NovelStructureTitle(revision.title),
                summary=NovelStructureSummary(revision.summary),
                position=NovelStructurePosition(revision.position),
                created_at=revision.created_at,
            ),
        )
    except (DomainError, TypeError, ValueError) as exc:
        raise NovelStructureDataCorruption from exc


def chapter_aggregate_to_records(
    aggregate: ChapterAggregate,
) -> tuple[ChapterRecord, ChapterHeadRecord, ChapterRevisionRecord]:
    if type(aggregate) is not ChapterAggregate:
        raise InvalidNovelStructureState
    return (
        ChapterRecord(
            id=aggregate.chapter.id,
            project_id=aggregate.chapter.project_id,
            volume_id=aggregate.chapter.volume_id,
            current_position=int(aggregate.current_revision.position),
            concurrency_version=aggregate.chapter.concurrency_version,
            created_at=aggregate.chapter.created_at,
            updated_at=aggregate.chapter.updated_at,
        ),
        ChapterHeadRecord(
            chapter_id=aggregate.head.chapter_id,
            revision_id=aggregate.head.revision_id,
            updated_at=aggregate.head.updated_at,
        ),
        chapter_revision_to_record(aggregate.current_revision),
    )


def chapter_revision_to_record(revision: ChapterRevision) -> ChapterRevisionRecord:
    if type(revision) is not ChapterRevision:
        raise InvalidNovelStructureState
    return ChapterRevisionRecord(
        id=revision.id,
        chapter_id=revision.chapter_id,
        revision_number=revision.revision_number,
        title=str(revision.title),
        summary=str(revision.summary),
        position=int(revision.position),
        created_at=revision.created_at,
    )


def chapter_aggregate_from_records(
    stable: ChapterRecord,
    head: ChapterHeadRecord,
    revision: ChapterRevisionRecord,
) -> ChapterAggregate:
    if (
        type(stable) is not ChapterRecord
        or type(head) is not ChapterHeadRecord
        or type(revision) is not ChapterRevisionRecord
        or stable.current_position != revision.position
    ):
        raise NovelStructureDataCorruption
    try:
        return ChapterAggregate(
            chapter=Chapter(
                id=stable.id,
                project_id=stable.project_id,
                volume_id=stable.volume_id,
                concurrency_version=stable.concurrency_version,
                created_at=stable.created_at,
                updated_at=stable.updated_at,
            ),
            head=ChapterHead(
                chapter_id=head.chapter_id,
                revision_id=head.revision_id,
                updated_at=head.updated_at,
            ),
            current_revision=ChapterRevision(
                id=revision.id,
                chapter_id=revision.chapter_id,
                revision_number=revision.revision_number,
                title=NovelStructureTitle(revision.title),
                summary=NovelStructureSummary(revision.summary),
                position=NovelStructurePosition(revision.position),
                created_at=revision.created_at,
            ),
        )
    except (DomainError, TypeError, ValueError) as exc:
        raise NovelStructureDataCorruption from exc


__all__ = [
    "chapter_aggregate_from_records",
    "chapter_aggregate_to_records",
    "chapter_revision_to_record",
    "outline_aggregate_from_records",
    "outline_aggregate_to_records",
    "outline_revision_to_record",
    "volume_aggregate_from_records",
    "volume_aggregate_to_records",
    "volume_revision_to_record",
]
