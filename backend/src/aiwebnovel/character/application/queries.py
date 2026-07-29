"""Immutable inputs and bounded rules for Character read use cases."""

from dataclasses import dataclass

from aiwebnovel.character.application.models import CharacterListPosition

DEFAULT_CHARACTER_LIST_LIMIT = 20
MAX_CHARACTER_LIST_LIMIT = 100


def validate_character_list_limit(limit: object) -> int:
    """Return a bounded list limit without coercing bools or numbers."""
    if type(limit) is not int or not 1 <= limit <= MAX_CHARACTER_LIST_LIMIT:
        raise ValueError("limit must be an integer from 1 through 100")
    return limit


@dataclass(frozen=True, slots=True)
class GetCharacterQuery:
    """Request the current complete snapshot for one Character."""

    character_id: str


@dataclass(frozen=True, slots=True)
class ListCharactersForProjectQuery:
    """Request one stable Character keyset page for a Project."""

    project_id: str
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT
    after: CharacterListPosition | None = None

    def __post_init__(self) -> None:
        validate_character_list_limit(self.limit)
        if self.after is not None and type(self.after) is not CharacterListPosition:
            raise TypeError("after must be a CharacterListPosition or None")


__all__ = [
    "DEFAULT_CHARACTER_LIST_LIMIT",
    "MAX_CHARACTER_LIST_LIMIT",
    "GetCharacterQuery",
    "ListCharactersForProjectQuery",
    "validate_character_list_limit",
]
