"""SQLAlchemy records owned by the Character module."""

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

from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
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

_CHARACTER_NAME_WHITESPACE_SQL = (
    "char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, "
    "8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, "
    "8232, 8233, 8239, 8287, 12288)"
)


class CharacterRecord(Base):
    """Stable Character identity, Project ownership, and concurrency."""

    __tablename__ = "characters"
    __table_args__ = (
        CheckConstraint(
            "concurrency_version > 0",
            name="ck_characters_concurrency_version_positive",
        ),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_characters_updated_at_not_before_created_at",
        ),
        Index("ix_characters_project_id", "project_id"),
    )

    id: Mapped[CharacterId] = mapped_column(
        PrefixedUlidType(CharacterId),
        primary_key=True,
    )
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId),
        ForeignKey(
            "projects.id",
            name="fk_characters_project_id_projects",
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


class CharacterRevisionRecord(Base):
    """Append-only complete Character card snapshot."""

    __tablename__ = "character_revisions"
    __table_args__ = (
        CheckConstraint(
            "revision_number > 0",
            name="ck_character_revisions_revision_number_positive",
        ),
        CheckConstraint(
            "length(name) BETWEEN 1 AND 120",
            name="ck_character_revisions_name_length",
        ),
        CheckConstraint(
            f"length(trim(name, {_CHARACTER_NAME_WHITESPACE_SQL})) > 0",
            name="ck_character_revisions_name_not_blank",
        ),
        CheckConstraint(
            "length(role) <= 120",
            name="ck_character_revisions_role_length",
        ),
        CheckConstraint(
            "length(profile) <= 50000",
            name="ck_character_revisions_profile_length",
        ),
        UniqueConstraint(
            "character_id",
            "revision_number",
            name="uq_character_revisions_owner_revision_number",
        ),
        UniqueConstraint(
            "character_id",
            "id",
            name="uq_character_revisions_owner_id",
        ),
    )

    id: Mapped[CharacterRevisionId] = mapped_column(
        PrefixedUlidType(CharacterRevisionId),
        primary_key=True,
    )
    character_id: Mapped[CharacterId] = mapped_column(
        PrefixedUlidType(CharacterId),
        ForeignKey(
            "characters.id",
            name="fk_character_revisions_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    revision_number: Mapped[RevisionNumber] = mapped_column(
        RevisionNumberType(),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text(120), nullable=False)
    role: Mapped[str] = mapped_column(Text(120), nullable=False)
    profile: Mapped[str] = mapped_column(Text(50_000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)

    def __repr__(self) -> str:
        """Return a diagnostic representation without user-authored text."""
        return "<CharacterRevisionRecord>"


class CharacterHeadRecord(Base):
    """Replaceable current-revision pointer with enforced ownership."""

    __tablename__ = "character_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ("character_id", "revision_id"),
            ("character_revisions.character_id", "character_revisions.id"),
            name="fk_character_heads_revision_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )

    character_id: Mapped[CharacterId] = mapped_column(
        PrefixedUlidType(CharacterId),
        ForeignKey(
            "characters.id",
            name="fk_character_heads_owner",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        primary_key=True,
    )
    revision_id: Mapped[CharacterRevisionId] = mapped_column(
        PrefixedUlidType(CharacterRevisionId),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(UtcDateTimeType(), nullable=False)


__all__ = ["CharacterHeadRecord", "CharacterRecord", "CharacterRevisionRecord"]
