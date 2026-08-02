"""Immutable primitive inputs for Character revision-history reads."""

from dataclasses import dataclass

from aiwebnovel.character.application.history_models import CharacterRevisionHistoryPosition
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber

DEFAULT_CHARACTER_REVISION_HISTORY_LIMIT = 20
MAX_CHARACTER_REVISION_HISTORY_LIMIT = 100


def validate_character_revision_history_limit(limit: object) -> int:
    if type(limit) is not int or not 1 <= limit <= MAX_CHARACTER_REVISION_HISTORY_LIMIT:
        raise ValueError("limit must be an integer from 1 through 100")
    return limit


def validate_character_revision_number(value: object) -> int:
    if type(value) is not int:
        raise ValueError("revision_number must be a positive signed-64 integer")
    assert isinstance(value, int)
    try:
        return int(RevisionNumber(value))
    except (DomainError, TypeError, ValueError):
        raise ValueError("revision_number must be a positive signed-64 integer") from None


@dataclass(frozen=True, slots=True)
class ListCharacterRevisionsQuery:
    character_id: str
    limit: int = DEFAULT_CHARACTER_REVISION_HISTORY_LIMIT
    after: CharacterRevisionHistoryPosition | None = None

    def __post_init__(self) -> None:
        if type(self.character_id) is not str:
            raise TypeError("character_id must be a string")
        validate_character_revision_history_limit(self.limit)
        if self.after is not None and type(self.after) is not CharacterRevisionHistoryPosition:
            raise TypeError("after must be a CharacterRevisionHistoryPosition or None")


@dataclass(frozen=True, slots=True)
class GetCharacterRevisionQuery:
    character_id: str
    revision_number: int

    def __post_init__(self) -> None:
        if type(self.character_id) is not str:
            raise TypeError("character_id must be a string")
        validate_character_revision_number(self.revision_number)


__all__ = [
    "DEFAULT_CHARACTER_REVISION_HISTORY_LIMIT",
    "MAX_CHARACTER_REVISION_HISTORY_LIMIT",
    "GetCharacterRevisionQuery",
    "ListCharacterRevisionsQuery",
    "validate_character_revision_history_limit",
    "validate_character_revision_number",
]
