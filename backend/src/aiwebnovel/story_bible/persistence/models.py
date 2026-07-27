"""SQLAlchemy records owned by the Story Bible module."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Text, UniqueConstraint
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
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId

_STORY_BIBLE_TITLE_WHITESPACE_SQL = (
    "char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, "
    "8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, "
    "8232, 8233, 8239, 8287, 12288)"
)


class StoryBibleRecord(Base):
    """Stable Story Bible identity, Project ownership, and concurrency."""

    __tablename__ = "story_bibles"
    __table_args__ = (
        CheckConstraint(
            "concurrency_version > 0",
            name="ck_story_bibles_concurrency_version_positive",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_story_bibles_updated_at_not_before_created_at",
        ),
        UniqueConstraint(
            "project_id",
            name="uq_story_bibles_project_id",
        ),
    )

    id: Mapped[StoryBibleId] = mapped_column(
        PrefixedUlidType(StoryBibleId),
        primary_key=True,
    )
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId),
        ForeignKey(
            "projects.id",
            name="fk_story_bibles_project_id_projects",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    concurrency_version: Mapped[ConcurrencyVersion] = mapped_column(
        ConcurrencyVersionType(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


class StoryBibleRevisionRecord(Base):
    """Append-only complete Story Bible text snapshot."""

    __tablename__ = "story_bible_revisions"
    __table_args__ = (
        CheckConstraint(
            "revision_number > 0",
            name="ck_story_bible_revisions_revision_number_positive",
        ),
        CheckConstraint(
            "length(title) BETWEEN 1 AND 120",
            name="ck_story_bible_revisions_title_length",
        ),
        CheckConstraint(
            f"length(trim(title, {_STORY_BIBLE_TITLE_WHITESPACE_SQL})) > 0",
            name="ck_story_bible_revisions_title_not_blank",
        ),
        CheckConstraint(
            "length(content) <= 50000",
            name="ck_story_bible_revisions_content_length",
        ),
        UniqueConstraint(
            "story_bible_id",
            "revision_number",
            name="uq_story_bible_revisions_owner_revision_number",
        ),
        UniqueConstraint(
            "story_bible_id",
            "id",
            name="uq_story_bible_revisions_owner_id",
        ),
    )

    id: Mapped[StoryBibleRevisionId] = mapped_column(
        PrefixedUlidType(StoryBibleRevisionId),
        primary_key=True,
    )
    story_bible_id: Mapped[StoryBibleId] = mapped_column(
        PrefixedUlidType(StoryBibleId),
        ForeignKey(
            "story_bibles.id",
            name="fk_story_bible_revisions_owner",
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
    content: Mapped[str] = mapped_column(Text(50_000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)

    def __repr__(self) -> str:
        """Return a diagnostic representation that never includes user text."""
        return "<StoryBibleRevisionRecord>"


class StoryBibleHeadRecord(Base):
    """Replaceable current-revision pointer with enforced ownership."""

    __tablename__ = "story_bible_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ("story_bible_id", "revision_id"),
            ("story_bible_revisions.story_bible_id", "story_bible_revisions.id"),
            name="fk_story_bible_heads_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    story_bible_id: Mapped[StoryBibleId] = mapped_column(
        PrefixedUlidType(StoryBibleId),
        ForeignKey(
            "story_bibles.id",
            name="fk_story_bible_heads_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    revision_id: Mapped[StoryBibleRevisionId] = mapped_column(
        PrefixedUlidType(StoryBibleRevisionId),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


__all__ = [
    "StoryBibleHeadRecord",
    "StoryBibleRecord",
    "StoryBibleRevisionRecord",
]
