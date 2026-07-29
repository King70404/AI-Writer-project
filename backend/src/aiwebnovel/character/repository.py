"""Framework-independent persistence contract owned by Character."""

from collections.abc import Callable
from typing import Protocol

from aiwebnovel.character.entities import CharacterAggregate
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock


class CharacterRepository(Protocol):
    """Store and restore only a Character's current aggregate."""

    def create(self, aggregate: CharacterAggregate) -> CharacterAggregate:
        """Atomically persist a stable object, revision one, and its head."""
        ...

    def get(self, character_id: CharacterId) -> CharacterAggregate | None:
        """Return one consistent current aggregate, or None when absent."""
        ...

    def append_revision(
        self,
        character_id: CharacterId,
        *,
        expected_version: ConcurrencyVersion,
        name: CharacterName,
        role: CharacterRole,
        profile: CharacterProfile,
        clock: Clock,
        revision_id_factory: Callable[[], CharacterRevisionId],
    ) -> CharacterAggregate:
        """Atomically append a complete revision using stable and head CAS."""
        ...


__all__ = ["CharacterRepository"]
