"""Pure Character creation and immutable revision transitions."""

from datetime import datetime

from aiwebnovel.character.entities import (
    Character,
    CharacterAggregate,
    CharacterHead,
    CharacterRevision,
    normalize_character_time,
)
from aiwebnovel.character.errors import InvalidCharacterState
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId


def create_initial_character(
    *,
    character_id: CharacterId,
    revision_id: CharacterRevisionId,
    project_id: ProjectId,
    name: CharacterName,
    role: CharacterRole,
    profile: CharacterProfile,
    now: datetime,
) -> CharacterAggregate:
    """Create revision one from caller-supplied values without side effects."""
    if (
        type(character_id) is not CharacterId
        or type(revision_id) is not CharacterRevisionId
        or type(project_id) is not ProjectId
        or type(name) is not CharacterName
        or type(role) is not CharacterRole
        or type(profile) is not CharacterProfile
    ):
        raise InvalidCharacterState
    normalized_now = normalize_character_time(now)
    character = Character(
        id=character_id,
        project_id=project_id,
        concurrency_version=ConcurrencyVersion(),
        created_at=normalized_now,
        updated_at=normalized_now,
    )
    revision = CharacterRevision(
        id=revision_id,
        character_id=character_id,
        revision_number=RevisionNumber(),
        name=name,
        role=role,
        profile=profile,
        created_at=normalized_now,
    )
    head = CharacterHead(
        character_id=character_id,
        revision_id=revision_id,
        updated_at=normalized_now,
    )
    return CharacterAggregate(
        character=character,
        head=head,
        current_revision=revision,
    )


def append_character_revision(
    aggregate: CharacterAggregate,
    *,
    expected_version: ConcurrencyVersion,
    revision_id: CharacterRevisionId,
    name: CharacterName,
    role: CharacterRole,
    profile: CharacterProfile,
    now: datetime,
) -> CharacterAggregate:
    """Append one complete revision after an optimistic-concurrency check."""
    if type(aggregate) is not CharacterAggregate:
        raise InvalidCharacterState
    assert_expected_version(
        actual=aggregate.character.concurrency_version,
        expected=expected_version,
    )
    if (
        type(revision_id) is not CharacterRevisionId
        or type(name) is not CharacterName
        or type(role) is not CharacterRole
        or type(profile) is not CharacterProfile
    ):
        raise InvalidCharacterState
    normalized_now = normalize_character_time(now)
    if normalized_now < aggregate.character.updated_at:
        raise InvalidCharacterState
    if revision_id == aggregate.current_revision.id:
        raise InvalidCharacterState

    character = Character(
        id=aggregate.character.id,
        project_id=aggregate.character.project_id,
        concurrency_version=aggregate.character.concurrency_version.next(),
        created_at=aggregate.character.created_at,
        updated_at=normalized_now,
    )
    revision = CharacterRevision(
        id=revision_id,
        character_id=aggregate.character.id,
        revision_number=aggregate.current_revision.revision_number.next(),
        name=name,
        role=role,
        profile=profile,
        created_at=normalized_now,
    )
    head = CharacterHead(
        character_id=aggregate.character.id,
        revision_id=revision_id,
        updated_at=normalized_now,
    )
    return CharacterAggregate(
        character=character,
        head=head,
        current_revision=revision,
    )
