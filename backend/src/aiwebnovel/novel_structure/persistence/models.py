"""SQLAlchemy records owned by the novel-structure module."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import (
    ConcurrencyVersionType,
    PrefixedUlidType,
    RevisionNumberType,
    UtcDateTimeType,
)
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.novel_structure.identifiers import (
    ChapterId,
    ChapterRevisionId,
    OutlineId,
    OutlineRevisionId,
    VolumeId,
    VolumeRevisionId,
)
from aiwebnovel.project.identifiers import ProjectId

_TITLE_WHITESPACE_SQL = (
    "char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, "
    "8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, "
    "8232, 8233, 8239, 8287, 12288)"
)


class OutlineRecord(Base):
    __tablename__ = "outlines"
    __table_args__ = (
        CheckConstraint("concurrency_version > 0", name="ck_outlines_version_positive"),
        CheckConstraint("updated_at >= created_at", name="ck_outlines_time_order"),
        UniqueConstraint("project_id", name="uq_outlines_project_id"),
    )

    id: Mapped[OutlineId] = mapped_column(PrefixedUlidType(OutlineId), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId),
        ForeignKey(
            "projects.id", name="fk_outlines_project", ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        nullable=False,
    )
    concurrency_version: Mapped[ConcurrencyVersion] = mapped_column(
        ConcurrencyVersionType(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


class OutlineRevisionRecord(Base):
    __tablename__ = "outline_revisions"
    __table_args__ = (
        CheckConstraint("revision_number > 0", name="ck_outline_revisions_number_positive"),
        CheckConstraint(
            "length(title) BETWEEN 1 AND 120", name="ck_outline_revisions_title_length"
        ),
        CheckConstraint(
            f"length(trim(title, {_TITLE_WHITESPACE_SQL})) > 0",
            name="ck_outline_revisions_title_not_blank",
        ),
        CheckConstraint("length(summary) <= 2000", name="ck_outline_revisions_summary_length"),
        UniqueConstraint("outline_id", "revision_number", name="uq_outline_revisions_owner_number"),
        UniqueConstraint("outline_id", "id", name="uq_outline_revisions_owner_id"),
    )

    id: Mapped[OutlineRevisionId] = mapped_column(
        PrefixedUlidType(OutlineRevisionId), primary_key=True
    )
    outline_id: Mapped[OutlineId] = mapped_column(
        PrefixedUlidType(OutlineId),
        ForeignKey(
            "outlines.id",
            name="fk_outline_revisions_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    revision_number: Mapped[RevisionNumber] = mapped_column(RevisionNumberType(), nullable=False)
    title: Mapped[str] = mapped_column(Text(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text(2_000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)

    def __repr__(self) -> str:
        return "<OutlineRevisionRecord>"


class OutlineHeadRecord(Base):
    __tablename__ = "outline_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ("outline_id", "revision_id"),
            ("outline_revisions.outline_id", "outline_revisions.id"),
            name="fk_outline_heads_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    outline_id: Mapped[OutlineId] = mapped_column(
        PrefixedUlidType(OutlineId),
        ForeignKey(
            "outlines.id", name="fk_outline_heads_owner", ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        primary_key=True,
    )
    revision_id: Mapped[OutlineRevisionId] = mapped_column(
        PrefixedUlidType(OutlineRevisionId), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


class VolumeRecord(Base):
    __tablename__ = "volumes"
    __table_args__ = (
        CheckConstraint("concurrency_version > 0", name="ck_volumes_version_positive"),
        CheckConstraint("current_position > 0", name="ck_volumes_position_positive"),
        CheckConstraint("updated_at >= created_at", name="ck_volumes_time_order"),
        UniqueConstraint("project_id", "current_position", name="uq_volumes_project_position"),
        Index("ix_volumes_project_id", "project_id"),
    )

    id: Mapped[VolumeId] = mapped_column(PrefixedUlidType(VolumeId), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId),
        ForeignKey(
            "projects.id", name="fk_volumes_project", ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        nullable=False,
    )
    current_position: Mapped[int] = mapped_column(nullable=False)
    concurrency_version: Mapped[ConcurrencyVersion] = mapped_column(
        ConcurrencyVersionType(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


class VolumeRevisionRecord(Base):
    __tablename__ = "volume_revisions"
    __table_args__ = (
        CheckConstraint("revision_number > 0", name="ck_volume_revisions_number_positive"),
        CheckConstraint("position > 0", name="ck_volume_revisions_position_positive"),
        CheckConstraint("length(title) BETWEEN 1 AND 120", name="ck_volume_revisions_title_length"),
        CheckConstraint(
            f"length(trim(title, {_TITLE_WHITESPACE_SQL})) > 0",
            name="ck_volume_revisions_title_not_blank",
        ),
        CheckConstraint("length(summary) <= 2000", name="ck_volume_revisions_summary_length"),
        UniqueConstraint("volume_id", "revision_number", name="uq_volume_revisions_owner_number"),
        UniqueConstraint("volume_id", "id", name="uq_volume_revisions_owner_id"),
    )

    id: Mapped[VolumeRevisionId] = mapped_column(
        PrefixedUlidType(VolumeRevisionId), primary_key=True
    )
    volume_id: Mapped[VolumeId] = mapped_column(
        PrefixedUlidType(VolumeId),
        ForeignKey(
            "volumes.id", name="fk_volume_revisions_owner", ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        nullable=False,
    )
    revision_number: Mapped[RevisionNumber] = mapped_column(RevisionNumberType(), nullable=False)
    title: Mapped[str] = mapped_column(Text(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text(2_000), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)

    def __repr__(self) -> str:
        return "<VolumeRevisionRecord>"


class VolumeHeadRecord(Base):
    __tablename__ = "volume_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ("volume_id", "revision_id"),
            ("volume_revisions.volume_id", "volume_revisions.id"),
            name="fk_volume_heads_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    volume_id: Mapped[VolumeId] = mapped_column(
        PrefixedUlidType(VolumeId),
        ForeignKey(
            "volumes.id", name="fk_volume_heads_owner", ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        primary_key=True,
    )
    revision_id: Mapped[VolumeRevisionId] = mapped_column(
        PrefixedUlidType(VolumeRevisionId), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


class ChapterRecord(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        CheckConstraint("concurrency_version > 0", name="ck_chapters_version_positive"),
        CheckConstraint("current_position > 0", name="ck_chapters_position_positive"),
        CheckConstraint("updated_at >= created_at", name="ck_chapters_time_order"),
        UniqueConstraint("volume_id", "current_position", name="uq_chapters_volume_position"),
        Index("ix_chapters_project_id", "project_id"),
        Index("ix_chapters_volume_id", "volume_id"),
    )

    id: Mapped[ChapterId] = mapped_column(PrefixedUlidType(ChapterId), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId),
        ForeignKey(
            "projects.id", name="fk_chapters_project", ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        nullable=False,
    )
    volume_id: Mapped[VolumeId] = mapped_column(
        PrefixedUlidType(VolumeId),
        ForeignKey(
            "volumes.id", name="fk_chapters_volume", ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        nullable=False,
    )
    current_position: Mapped[int] = mapped_column(nullable=False)
    concurrency_version: Mapped[ConcurrencyVersion] = mapped_column(
        ConcurrencyVersionType(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


class ChapterRevisionRecord(Base):
    __tablename__ = "chapter_revisions"
    __table_args__ = (
        CheckConstraint("revision_number > 0", name="ck_chapter_revisions_number_positive"),
        CheckConstraint("position > 0", name="ck_chapter_revisions_position_positive"),
        CheckConstraint(
            "length(title) BETWEEN 1 AND 120", name="ck_chapter_revisions_title_length"
        ),
        CheckConstraint(
            f"length(trim(title, {_TITLE_WHITESPACE_SQL})) > 0",
            name="ck_chapter_revisions_title_not_blank",
        ),
        CheckConstraint("length(summary) <= 2000", name="ck_chapter_revisions_summary_length"),
        UniqueConstraint("chapter_id", "revision_number", name="uq_chapter_revisions_owner_number"),
        UniqueConstraint("chapter_id", "id", name="uq_chapter_revisions_owner_id"),
    )

    id: Mapped[ChapterRevisionId] = mapped_column(
        PrefixedUlidType(ChapterRevisionId), primary_key=True
    )
    chapter_id: Mapped[ChapterId] = mapped_column(
        PrefixedUlidType(ChapterId),
        ForeignKey(
            "chapters.id",
            name="fk_chapter_revisions_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    revision_number: Mapped[RevisionNumber] = mapped_column(RevisionNumberType(), nullable=False)
    title: Mapped[str] = mapped_column(Text(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text(2_000), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)

    def __repr__(self) -> str:
        return "<ChapterRevisionRecord>"


class ChapterHeadRecord(Base):
    __tablename__ = "chapter_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ("chapter_id", "revision_id"),
            ("chapter_revisions.chapter_id", "chapter_revisions.id"),
            name="fk_chapter_heads_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    chapter_id: Mapped[ChapterId] = mapped_column(
        PrefixedUlidType(ChapterId),
        ForeignKey(
            "chapters.id", name="fk_chapter_heads_owner", ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        primary_key=True,
    )
    revision_id: Mapped[ChapterRevisionId] = mapped_column(
        PrefixedUlidType(ChapterRevisionId), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


__all__ = [
    "ChapterHeadRecord",
    "ChapterRecord",
    "ChapterRevisionRecord",
    "OutlineHeadRecord",
    "OutlineRecord",
    "OutlineRevisionRecord",
    "VolumeHeadRecord",
    "VolumeRecord",
    "VolumeRevisionRecord",
]
