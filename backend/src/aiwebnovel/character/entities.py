"""Immutable Character entities and current-aggregate invariants."""

from dataclasses import dataclass
from datetime import datetime

from aiwebnovel.character.errors import InvalidCharacterState
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.identifiers import ProjectId


def normalize_character_time(value: object) -> datetime:
    """Normalize an exact datetime to UTC without retaining invalid input."""
    if type(value) is not datetime:
        raise InvalidCharacterState
    try:
        return ensure_utc(value)
    except ValueError:
        raise InvalidCharacterState from None


@dataclass(frozen=True, slots=True)
class Character:
    """Stable Character identity, Project ownership, and concurrency state."""

    id: CharacterId
    project_id: ProjectId
    concurrency_version: ConcurrencyVersion
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not CharacterId
            or type(self.project_id) is not ProjectId
            or type(self.concurrency_version) is not ConcurrencyVersion
        ):
            raise InvalidCharacterState
        created_at = normalize_character_time(self.created_at)
        updated_at = normalize_character_time(self.updated_at)
        if updated_at < created_at:
            raise InvalidCharacterState
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


@dataclass(frozen=True, slots=True)
class CharacterRevision:
    """One immutable complete Character card snapshot."""

    id: CharacterRevisionId
    character_id: CharacterId
    revision_number: RevisionNumber
    name: CharacterName
    role: CharacterRole
    profile: CharacterProfile
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not CharacterRevisionId
            or type(self.character_id) is not CharacterId
            or type(self.revision_number) is not RevisionNumber
            or type(self.name) is not CharacterName
            or type(self.role) is not CharacterRole
            or type(self.profile) is not CharacterProfile
        ):
            raise InvalidCharacterState
        object.__setattr__(self, "created_at", normalize_character_time(self.created_at))


@dataclass(frozen=True, slots=True)
class CharacterHead:
    """The authoritative pointer to one current immutable revision."""

    character_id: CharacterId
    revision_id: CharacterRevisionId
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.character_id) is not CharacterId
            or type(self.revision_id) is not CharacterRevisionId
        ):
            raise InvalidCharacterState
        object.__setattr__(self, "updated_at", normalize_character_time(self.updated_at))


@dataclass(frozen=True, slots=True)
class CharacterAggregate:
    """A consistent current Character view without revision history."""

    character: Character
    head: CharacterHead
    current_revision: CharacterRevision

    def __post_init__(self) -> None:
        if (
            type(self.character) is not Character
            or type(self.head) is not CharacterHead
            or type(self.current_revision) is not CharacterRevision
            or self.head.character_id != self.character.id
            or self.current_revision.character_id != self.character.id
            or self.head.revision_id != self.current_revision.id
            or self.character.concurrency_version.value
            != self.current_revision.revision_number.value
            or self.character.updated_at != self.head.updated_at
            or self.character.updated_at != self.current_revision.created_at
            or self.character.created_at > self.character.updated_at
            or self.current_revision.created_at < self.character.created_at
        ):
            raise InvalidCharacterState
