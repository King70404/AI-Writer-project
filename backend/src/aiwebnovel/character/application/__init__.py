"""Public pure-Python Character application contracts."""

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)
from aiwebnovel.character.application.errors import CharacterRevisionNotFound
from aiwebnovel.character.application.history_models import (
    CharacterRevisionHistoryItem,
    CharacterRevisionHistoryPage,
    CharacterRevisionHistoryPosition,
    CharacterRevisionSnapshot,
)
from aiwebnovel.character.application.history_queries import (
    DEFAULT_CHARACTER_REVISION_HISTORY_LIMIT,
    MAX_CHARACTER_REVISION_HISTORY_LIMIT,
    GetCharacterRevisionQuery,
    ListCharacterRevisionsQuery,
)
from aiwebnovel.character.application.history_reader import CharacterRevisionHistoryReader
from aiwebnovel.character.application.history_service import CharacterRevisionHistoryQueryService
from aiwebnovel.character.application.list_reader import CharacterListReader
from aiwebnovel.character.application.mappers import (
    character_snapshot_from_aggregate,
)
from aiwebnovel.character.application.models import (
    CharacterListItem,
    CharacterListPage,
    CharacterListPosition,
    CharacterSnapshot,
)
from aiwebnovel.character.application.queries import (
    DEFAULT_CHARACTER_LIST_LIMIT,
    MAX_CHARACTER_LIST_LIMIT,
    GetCharacterQuery,
    ListCharactersForProjectQuery,
)
from aiwebnovel.character.application.services import (
    CharacterCommandService,
    CharacterQueryService,
)

__all__ = [
    "DEFAULT_CHARACTER_LIST_LIMIT",
    "DEFAULT_CHARACTER_REVISION_HISTORY_LIMIT",
    "MAX_CHARACTER_LIST_LIMIT",
    "MAX_CHARACTER_REVISION_HISTORY_LIMIT",
    "CharacterCommandService",
    "CharacterListItem",
    "CharacterListPage",
    "CharacterListPosition",
    "CharacterListReader",
    "CharacterQueryService",
    "CharacterRevisionHistoryItem",
    "CharacterRevisionHistoryPage",
    "CharacterRevisionHistoryPosition",
    "CharacterRevisionHistoryQueryService",
    "CharacterRevisionHistoryReader",
    "CharacterRevisionNotFound",
    "CharacterRevisionSnapshot",
    "CharacterSnapshot",
    "CreateCharacterCommand",
    "GetCharacterQuery",
    "GetCharacterRevisionQuery",
    "ListCharacterRevisionsQuery",
    "ListCharactersForProjectQuery",
    "ReviseCharacterCommand",
    "character_snapshot_from_aggregate",
]
