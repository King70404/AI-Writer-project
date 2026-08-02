"""Character immutable revision-history query service."""

from aiwebnovel.character.application.errors import CharacterRevisionNotFound
from aiwebnovel.character.application.history_models import (
    CharacterRevisionHistoryPage,
    CharacterRevisionSnapshot,
)
from aiwebnovel.character.application.history_queries import (
    GetCharacterRevisionQuery,
    ListCharacterRevisionsQuery,
    validate_character_revision_history_limit,
)
from aiwebnovel.character.application.history_reader import CharacterRevisionHistoryReader
from aiwebnovel.character.identifiers import CharacterId
from aiwebnovel.domain.revisions import RevisionNumber


class CharacterRevisionHistoryQueryService:
    def __init__(self, reader: CharacterRevisionHistoryReader) -> None:
        self._reader = reader

    def list_revisions(self, query: ListCharacterRevisionsQuery) -> CharacterRevisionHistoryPage:
        if type(query) is not ListCharacterRevisionsQuery:
            raise TypeError("query must be a ListCharacterRevisionsQuery")
        character_id = CharacterId.parse(query.character_id)
        limit = validate_character_revision_history_limit(query.limit)
        if query.after is not None and query.after.character_id != character_id:
            raise ValueError("after position must belong to the requested Character")
        return self._reader.list_revisions(character_id, limit=limit, after=query.after)

    def get_revision(self, query: GetCharacterRevisionQuery) -> CharacterRevisionSnapshot:
        if type(query) is not GetCharacterRevisionQuery:
            raise TypeError("query must be a GetCharacterRevisionQuery")
        character_id = CharacterId.parse(query.character_id)
        revision_number = RevisionNumber(query.revision_number)
        snapshot = self._reader.get_revision(character_id, revision_number)
        if snapshot is None:
            raise CharacterRevisionNotFound(character_id, revision_number)
        return snapshot


__all__ = ["CharacterRevisionHistoryQueryService"]
