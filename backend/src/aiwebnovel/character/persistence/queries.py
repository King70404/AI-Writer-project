"""Deterministic SQLAlchemy statements for Character persistence."""

from datetime import datetime

from sqlalchemy import Select, Update, and_, select, update

from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.persistence.models import (
    CharacterHeadRecord,
    CharacterRecord,
    CharacterRevisionRecord,
)
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import ProjectRecord


def project_exists_query(project_id: ProjectId) -> Select[tuple[ProjectId]]:
    """Select only the Project ownership identity needed by this module."""
    return select(ProjectRecord.id).where(ProjectRecord.id == project_id)


def character_identity_query(
    character_id: CharacterId,
) -> Select[tuple[CharacterId]]:
    """Select a stable Character identity without loading card text."""
    return select(CharacterRecord.id).where(CharacterRecord.id == character_id)


def current_character_query(
    character_id: CharacterId,
) -> Select[
    tuple[
        CharacterRecord,
        ProjectId,
        CharacterHeadRecord,
        CharacterRevisionRecord,
    ]
]:
    """Select one Character, its owner, explicit head, and current revision."""
    return (
        select(
            CharacterRecord,
            ProjectRecord.id,
            CharacterHeadRecord,
            CharacterRevisionRecord,
        )
        .outerjoin(ProjectRecord, ProjectRecord.id == CharacterRecord.project_id)
        .outerjoin(
            CharacterHeadRecord,
            CharacterHeadRecord.character_id == CharacterRecord.id,
        )
        .outerjoin(
            CharacterRevisionRecord,
            and_(
                CharacterRevisionRecord.character_id == CharacterHeadRecord.character_id,
                CharacterRevisionRecord.id == CharacterHeadRecord.revision_id,
            ),
        )
        .where(CharacterRecord.id == character_id)
    )


def character_compare_and_swap(
    character_id: CharacterId,
    expected_version: ConcurrencyVersion,
    new_version: ConcurrencyVersion,
    updated_at: datetime,
) -> Update:
    """Update only version and time when the stable version still matches."""
    return (
        update(CharacterRecord)
        .where(
            CharacterRecord.id == character_id,
            CharacterRecord.concurrency_version == expected_version,
        )
        .values(concurrency_version=new_version, updated_at=updated_at)
    )


def character_head_compare_and_swap(
    character_id: CharacterId,
    expected_revision_id: CharacterRevisionId,
    new_revision_id: CharacterRevisionId,
    updated_at: datetime,
) -> Update:
    """Move the explicit head only when it targets the expected revision."""
    return (
        update(CharacterHeadRecord)
        .where(
            CharacterHeadRecord.character_id == character_id,
            CharacterHeadRecord.revision_id == expected_revision_id,
        )
        .values(revision_id=new_revision_id, updated_at=updated_at)
    )


__all__ = [
    "character_compare_and_swap",
    "character_head_compare_and_swap",
    "character_identity_query",
    "current_character_query",
    "project_exists_query",
]
