"""SQLAlchemy records owned by the Project module."""

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
from aiwebnovel.project import (
    ConcurrencyVersion,
    ProjectId,
    ProjectRevisionId,
    RevisionNumber,
)

_PROJECT_TITLE_WHITESPACE_SQL = (
    "char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, "
    "8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, "
    "8232, 8233, 8239, 8287, 12288)"
)


class ProjectRecord(Base):
    """Stable Project identity and optimistic-concurrency persistence record."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "concurrency_version > 0",
            name="ck_projects_concurrency_version_positive",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_projects_updated_at_not_before_created_at",
        ),
    )

    id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId),
        primary_key=True,
    )
    concurrency_version: Mapped[ConcurrencyVersion] = mapped_column(
        ConcurrencyVersionType(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


class ProjectRevisionRecord(Base):
    """Append-only immutable Project revision persistence record."""

    __tablename__ = "project_revisions"
    __table_args__ = (
        CheckConstraint(
            "revision_number > 0",
            name="ck_project_revisions_revision_number_positive",
        ),
        CheckConstraint(
            "length(title) BETWEEN 1 AND 120",
            name="ck_project_revisions_title_length",
        ),
        CheckConstraint(
            f"length(trim(title, {_PROJECT_TITLE_WHITESPACE_SQL})) > 0",
            name="ck_project_revisions_title_not_blank",
        ),
        CheckConstraint(
            "length(description) <= 2000",
            name="ck_project_revisions_description_length",
        ),
        UniqueConstraint(
            "project_id",
            "revision_number",
            name="uq_project_revisions_project_revision_number",
        ),
        UniqueConstraint(
            "project_id",
            "id",
            name="uq_project_revisions_project_id_id",
        ),
        Index(
            "ix_project_revisions_project_id_revision_number",
            "project_id",
            "revision_number",
        ),
    )

    id: Mapped[ProjectRevisionId] = mapped_column(
        PrefixedUlidType(ProjectRevisionId),
        primary_key=True,
    )
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId),
        ForeignKey(
            "projects.id",
            name="fk_project_revisions_project_id_projects",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    revision_number: Mapped[RevisionNumber] = mapped_column(
        RevisionNumberType(),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text(120), nullable=False)
    description: Mapped[str] = mapped_column(Text(2_000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


class ProjectHeadRecord(Base):
    """Replaceable current-revision pointer with database-enforced ownership."""

    __tablename__ = "project_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ("project_id", "revision_id"),
            ("project_revisions.project_id", "project_revisions.id"),
            name="fk_project_heads_project_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId),
        ForeignKey(
            "projects.id",
            name="fk_project_heads_project_id_projects",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    revision_id: Mapped[ProjectRevisionId] = mapped_column(
        PrefixedUlidType(ProjectRevisionId),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


__all__ = ["ProjectHeadRecord", "ProjectRecord", "ProjectRevisionRecord"]
