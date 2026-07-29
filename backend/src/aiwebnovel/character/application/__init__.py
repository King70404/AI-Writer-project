"""Public pure-Python Character application contracts."""

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)
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
    "MAX_CHARACTER_LIST_LIMIT",
    "CharacterCommandService",
    "CharacterListItem",
    "CharacterListPage",
    "CharacterListPosition",
    "CharacterListReader",
    "CharacterQueryService",
    "CharacterSnapshot",
    "CreateCharacterCommand",
    "GetCharacterQuery",
    "ListCharactersForProjectQuery",
    "ReviseCharacterCommand",
    "character_snapshot_from_aggregate",
]
