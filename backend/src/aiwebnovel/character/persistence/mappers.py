"""Explicit mappings between Character domain values and records."""

from aiwebnovel.character.entities import (
    Character,
    CharacterAggregate,
    CharacterHead,
    CharacterRevision,
)
from aiwebnovel.character.errors import CharacterDataCorruption, InvalidCharacterState
from aiwebnovel.character.persistence.models import (
    CharacterHeadRecord,
    CharacterRecord,
    CharacterRevisionRecord,
)
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.errors import DomainError


def character_to_record(character: Character) -> CharacterRecord:
    """Copy one validated stable object into a transient record."""
    if type(character) is not Character:
        raise InvalidCharacterState
    return CharacterRecord(
        id=character.id,
        project_id=character.project_id,
        concurrency_version=character.concurrency_version,
        created_at=character.created_at,
        updated_at=character.updated_at,
    )


def character_revision_to_record(
    revision: CharacterRevision,
) -> CharacterRevisionRecord:
    """Copy one immutable complete card into a transient record."""
    if type(revision) is not CharacterRevision:
        raise InvalidCharacterState
    return CharacterRevisionRecord(
        id=revision.id,
        character_id=revision.character_id,
        revision_number=revision.revision_number,
        name=str(revision.name),
        role=str(revision.role),
        profile=str(revision.profile),
        created_at=revision.created_at,
    )


def character_head_to_record(head: CharacterHead) -> CharacterHeadRecord:
    """Copy one current pointer into a transient record."""
    if type(head) is not CharacterHead:
        raise InvalidCharacterState
    return CharacterHeadRecord(
        character_id=head.character_id,
        revision_id=head.revision_id,
        updated_at=head.updated_at,
    )


def character_from_record(record: CharacterRecord) -> Character:
    """Restore one stable object and reject invalid stored values."""
    if type(record) is not CharacterRecord:
        raise CharacterDataCorruption
    try:
        return Character(
            id=record.id,
            project_id=record.project_id,
            concurrency_version=record.concurrency_version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
    except (DomainError, TypeError, ValueError) as exc:
        raise CharacterDataCorruption from exc


def character_revision_from_record(
    record: CharacterRevisionRecord,
) -> CharacterRevision:
    """Restore one revision and reapply all card value rules."""
    if type(record) is not CharacterRevisionRecord:
        raise CharacterDataCorruption
    try:
        return CharacterRevision(
            id=record.id,
            character_id=record.character_id,
            revision_number=record.revision_number,
            name=CharacterName(record.name),
            role=CharacterRole(record.role),
            profile=CharacterProfile(record.profile),
            created_at=record.created_at,
        )
    except (DomainError, TypeError, ValueError) as exc:
        raise CharacterDataCorruption from exc


def character_head_from_record(record: CharacterHeadRecord) -> CharacterHead:
    """Restore one current pointer and reject invalid stored values."""
    if type(record) is not CharacterHeadRecord:
        raise CharacterDataCorruption
    try:
        return CharacterHead(
            character_id=record.character_id,
            revision_id=record.revision_id,
            updated_at=record.updated_at,
        )
    except (DomainError, TypeError, ValueError) as exc:
        raise CharacterDataCorruption from exc


def character_aggregate_to_records(
    aggregate: CharacterAggregate,
) -> tuple[CharacterRecord, CharacterHeadRecord, CharacterRevisionRecord]:
    """Map one consistent aggregate to three transient records."""
    if type(aggregate) is not CharacterAggregate:
        raise InvalidCharacterState
    return (
        character_to_record(aggregate.character),
        character_head_to_record(aggregate.head),
        character_revision_to_record(aggregate.current_revision),
    )


def character_aggregate_from_records(
    character_record: CharacterRecord,
    head_record: CharacterHeadRecord,
    revision_record: CharacterRevisionRecord,
) -> CharacterAggregate:
    """Restore a fully validated current aggregate without database access."""
    try:
        return CharacterAggregate(
            character=character_from_record(character_record),
            head=character_head_from_record(head_record),
            current_revision=character_revision_from_record(revision_record),
        )
    except CharacterDataCorruption:
        raise
    except (DomainError, TypeError, ValueError) as exc:
        raise CharacterDataCorruption from exc


__all__ = [
    "character_aggregate_from_records",
    "character_aggregate_to_records",
    "character_from_record",
    "character_head_from_record",
    "character_head_to_record",
    "character_revision_from_record",
    "character_revision_to_record",
    "character_to_record",
]
