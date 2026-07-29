"""Public framework-independent Character domain contracts."""

from aiwebnovel.character.entities import (
    Character,
    CharacterAggregate,
    CharacterHead,
    CharacterRevision,
)
from aiwebnovel.character.errors import (
    CharacterDomainError,
    InvalidCharacterName,
    InvalidCharacterProfile,
    InvalidCharacterRole,
    InvalidCharacterState,
)
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.transitions import (
    append_character_revision,
    create_initial_character,
)
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidDomainIdentifier
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId

__all__ = [
    "Character",
    "CharacterAggregate",
    "CharacterDomainError",
    "CharacterHead",
    "CharacterId",
    "CharacterName",
    "CharacterProfile",
    "CharacterRevision",
    "CharacterRevisionId",
    "CharacterRole",
    "ConcurrencyConflict",
    "ConcurrencyVersion",
    "InvalidCharacterName",
    "InvalidCharacterProfile",
    "InvalidCharacterRole",
    "InvalidCharacterState",
    "InvalidDomainIdentifier",
    "ProjectId",
    "RevisionNumber",
    "append_character_revision",
    "create_initial_character",
]
