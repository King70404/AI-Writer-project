"""Deterministic SQLAlchemy statements for novel-structure persistence."""

from datetime import datetime

from sqlalchemy import Select, Update, and_, select, update

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.novel_structure.identifiers import ChapterId, OutlineId, VolumeId
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
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import ProjectRecord


def project_exists_query(project_id: ProjectId) -> Select[tuple[ProjectId]]:
    return select(ProjectRecord.id).where(ProjectRecord.id == project_id)


def outline_identity_query(outline_id: OutlineId) -> Select[tuple[OutlineId]]:
    return select(OutlineRecord.id).where(OutlineRecord.id == outline_id)


def outline_for_project_identity_query(project_id: ProjectId) -> Select[tuple[OutlineId]]:
    return select(OutlineRecord.id).where(OutlineRecord.project_id == project_id)


def current_outline_query(
    outline_id: OutlineId,
) -> Select[tuple[OutlineRecord, ProjectId, OutlineHeadRecord, OutlineRevisionRecord]]:
    return (
        select(OutlineRecord, ProjectRecord.id, OutlineHeadRecord, OutlineRevisionRecord)
        .outerjoin(ProjectRecord, ProjectRecord.id == OutlineRecord.project_id)
        .outerjoin(OutlineHeadRecord, OutlineHeadRecord.outline_id == OutlineRecord.id)
        .outerjoin(
            OutlineRevisionRecord,
            and_(
                OutlineRevisionRecord.outline_id == OutlineHeadRecord.outline_id,
                OutlineRevisionRecord.id == OutlineHeadRecord.revision_id,
            ),
        )
        .where(OutlineRecord.id == outline_id)
    )


def current_outline_for_project_query(
    project_id: ProjectId,
) -> Select[tuple[OutlineRecord, ProjectId, OutlineHeadRecord, OutlineRevisionRecord]]:
    return (
        select(OutlineRecord, ProjectRecord.id, OutlineHeadRecord, OutlineRevisionRecord)
        .outerjoin(ProjectRecord, ProjectRecord.id == OutlineRecord.project_id)
        .outerjoin(OutlineHeadRecord, OutlineHeadRecord.outline_id == OutlineRecord.id)
        .outerjoin(
            OutlineRevisionRecord,
            and_(
                OutlineRevisionRecord.outline_id == OutlineHeadRecord.outline_id,
                OutlineRevisionRecord.id == OutlineHeadRecord.revision_id,
            ),
        )
        .where(OutlineRecord.project_id == project_id)
    )


def volume_identity_query(volume_id: VolumeId) -> Select[tuple[VolumeId]]:
    return select(VolumeRecord.id).where(VolumeRecord.id == volume_id)


def volume_owner_query(volume_id: VolumeId) -> Select[tuple[ProjectId]]:
    return select(VolumeRecord.project_id).where(VolumeRecord.id == volume_id)


def volume_position_query(
    project_id: ProjectId,
    position: int,
    *,
    exclude_id: VolumeId | None = None,
) -> Select[tuple[VolumeId]]:
    statement = select(VolumeRecord.id).where(
        VolumeRecord.project_id == project_id,
        VolumeRecord.current_position == position,
    )
    return statement if exclude_id is None else statement.where(VolumeRecord.id != exclude_id)


def current_volume_query(
    volume_id: VolumeId,
) -> Select[tuple[VolumeRecord, ProjectId, VolumeHeadRecord, VolumeRevisionRecord]]:
    return (
        select(VolumeRecord, ProjectRecord.id, VolumeHeadRecord, VolumeRevisionRecord)
        .outerjoin(ProjectRecord, ProjectRecord.id == VolumeRecord.project_id)
        .outerjoin(VolumeHeadRecord, VolumeHeadRecord.volume_id == VolumeRecord.id)
        .outerjoin(
            VolumeRevisionRecord,
            and_(
                VolumeRevisionRecord.volume_id == VolumeHeadRecord.volume_id,
                VolumeRevisionRecord.id == VolumeHeadRecord.revision_id,
            ),
        )
        .where(VolumeRecord.id == volume_id)
    )


def volumes_for_project_query(
    project_id: ProjectId,
) -> Select[tuple[VolumeRecord, ProjectId, VolumeHeadRecord, VolumeRevisionRecord]]:
    return (
        select(VolumeRecord, ProjectRecord.id, VolumeHeadRecord, VolumeRevisionRecord)
        .outerjoin(ProjectRecord, ProjectRecord.id == VolumeRecord.project_id)
        .outerjoin(VolumeHeadRecord, VolumeHeadRecord.volume_id == VolumeRecord.id)
        .outerjoin(
            VolumeRevisionRecord,
            and_(
                VolumeRevisionRecord.volume_id == VolumeHeadRecord.volume_id,
                VolumeRevisionRecord.id == VolumeHeadRecord.revision_id,
            ),
        )
        .where(VolumeRecord.project_id == project_id)
        .order_by(VolumeRecord.current_position, VolumeRecord.id)
    )


def chapter_identity_query(chapter_id: ChapterId) -> Select[tuple[ChapterId]]:
    return select(ChapterRecord.id).where(ChapterRecord.id == chapter_id)


def chapter_position_query(
    volume_id: VolumeId,
    position: int,
    *,
    exclude_id: ChapterId | None = None,
) -> Select[tuple[ChapterId]]:
    statement = select(ChapterRecord.id).where(
        ChapterRecord.volume_id == volume_id,
        ChapterRecord.current_position == position,
    )
    return statement if exclude_id is None else statement.where(ChapterRecord.id != exclude_id)


def current_chapter_query(
    chapter_id: ChapterId,
) -> Select[tuple[ChapterRecord, ProjectId, ProjectId, ChapterHeadRecord, ChapterRevisionRecord]]:
    return (
        select(
            ChapterRecord,
            ProjectRecord.id,
            VolumeRecord.project_id,
            ChapterHeadRecord,
            ChapterRevisionRecord,
        )
        .outerjoin(ProjectRecord, ProjectRecord.id == ChapterRecord.project_id)
        .outerjoin(VolumeRecord, VolumeRecord.id == ChapterRecord.volume_id)
        .outerjoin(ChapterHeadRecord, ChapterHeadRecord.chapter_id == ChapterRecord.id)
        .outerjoin(
            ChapterRevisionRecord,
            and_(
                ChapterRevisionRecord.chapter_id == ChapterHeadRecord.chapter_id,
                ChapterRevisionRecord.id == ChapterHeadRecord.revision_id,
            ),
        )
        .where(ChapterRecord.id == chapter_id)
    )


def chapters_for_volume_query(
    volume_id: VolumeId,
) -> Select[tuple[ChapterRecord, ProjectId, ProjectId, ChapterHeadRecord, ChapterRevisionRecord]]:
    return (
        select(
            ChapterRecord,
            ProjectRecord.id,
            VolumeRecord.project_id,
            ChapterHeadRecord,
            ChapterRevisionRecord,
        )
        .outerjoin(ProjectRecord, ProjectRecord.id == ChapterRecord.project_id)
        .outerjoin(VolumeRecord, VolumeRecord.id == ChapterRecord.volume_id)
        .outerjoin(ChapterHeadRecord, ChapterHeadRecord.chapter_id == ChapterRecord.id)
        .outerjoin(
            ChapterRevisionRecord,
            and_(
                ChapterRevisionRecord.chapter_id == ChapterHeadRecord.chapter_id,
                ChapterRevisionRecord.id == ChapterHeadRecord.revision_id,
            ),
        )
        .where(ChapterRecord.volume_id == volume_id)
        .order_by(ChapterRecord.current_position, ChapterRecord.id)
    )


def stable_compare_and_swap(
    record_type: type[OutlineRecord] | type[VolumeRecord] | type[ChapterRecord],
    stable_id: OutlineId | VolumeId | ChapterId,
    expected_version: ConcurrencyVersion,
    new_version: ConcurrencyVersion,
    updated_at: datetime,
    *,
    current_position: int | None = None,
) -> Update:
    values: dict[str, object] = {"concurrency_version": new_version, "updated_at": updated_at}
    if current_position is not None:
        values["current_position"] = current_position
    return (
        update(record_type)
        .where(record_type.id == stable_id, record_type.concurrency_version == expected_version)
        .values(**values)
    )


def outline_head_compare_and_swap(
    outline_id: OutlineId,
    expected_revision_id: object,
    new_revision_id: object,
    updated_at: datetime,
) -> Update:
    return (
        update(OutlineHeadRecord)
        .where(
            OutlineHeadRecord.outline_id == outline_id,
            OutlineHeadRecord.revision_id == expected_revision_id,
        )
        .values(revision_id=new_revision_id, updated_at=updated_at)
    )


def volume_head_compare_and_swap(
    volume_id: VolumeId,
    expected_revision_id: object,
    new_revision_id: object,
    updated_at: datetime,
) -> Update:
    return (
        update(VolumeHeadRecord)
        .where(
            VolumeHeadRecord.volume_id == volume_id,
            VolumeHeadRecord.revision_id == expected_revision_id,
        )
        .values(revision_id=new_revision_id, updated_at=updated_at)
    )


def chapter_head_compare_and_swap(
    chapter_id: ChapterId,
    expected_revision_id: object,
    new_revision_id: object,
    updated_at: datetime,
) -> Update:
    return (
        update(ChapterHeadRecord)
        .where(
            ChapterHeadRecord.chapter_id == chapter_id,
            ChapterHeadRecord.revision_id == expected_revision_id,
        )
        .values(revision_id=new_revision_id, updated_at=updated_at)
    )
