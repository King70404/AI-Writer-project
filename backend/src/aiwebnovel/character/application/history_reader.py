"""Pure read port for immutable Character revision history."""

from typing import Protocol

from aiwebnovel.character.application.history_models import (
    CharacterRevisionHistoryPage,
    CharacterRevisionHistoryPosition,
    CharacterRevisionSnapshot,
)
from aiwebnovel.character.identifiers import CharacterId
from aiwebnovel.domain.revisions import RevisionNumber


class CharacterRevisionHistoryReader(Protocol):
    def list_revisions(
        self,
        character_id: CharacterId,
        *,
        limit: int,
        after: CharacterRevisionHistoryPosition | None,
    ) -> CharacterRevisionHistoryPage: ...

    def get_revision(
        self,
        character_id: CharacterId,
        revision_number: RevisionNumber,
    ) -> CharacterRevisionSnapshot | None: ...


__all__ = ["CharacterRevisionHistoryReader"]
