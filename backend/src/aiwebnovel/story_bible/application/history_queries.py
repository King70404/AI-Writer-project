"""Immutable primitive inputs for Story Bible revision-history reads."""

from dataclasses import dataclass

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.story_bible.application.history_models import (
    StoryBibleRevisionHistoryPosition,
)

DEFAULT_STORY_BIBLE_REVISION_HISTORY_LIMIT = 20
MAX_STORY_BIBLE_REVISION_HISTORY_LIMIT = 100


def validate_story_bible_revision_history_limit(limit: object) -> int:
    """Return a bounded history limit without coercing bools or other values."""
    if type(limit) is not int or not 1 <= limit <= MAX_STORY_BIBLE_REVISION_HISTORY_LIMIT:
        raise ValueError("limit must be an integer from 1 through 100")
    return limit


def validate_story_bible_revision_number(value: object) -> int:
    """Return one positive signed-64 RevisionNumber without coercion."""
    if type(value) is not int:
        raise ValueError("revision_number must be a positive signed-64 integer")
    assert isinstance(value, int)
    try:
        return int(RevisionNumber(value))
    except (DomainError, TypeError, ValueError):
        raise ValueError("revision_number must be a positive signed-64 integer") from None


@dataclass(frozen=True, slots=True)
class ListStoryBibleRevisionsQuery:
    """Request one fixed descending revision-history page."""

    story_bible_id: str
    limit: int = DEFAULT_STORY_BIBLE_REVISION_HISTORY_LIMIT
    after: StoryBibleRevisionHistoryPosition | None = None

    def __post_init__(self) -> None:
        if type(self.story_bible_id) is not str:
            raise TypeError("story_bible_id must be a string")
        validate_story_bible_revision_history_limit(self.limit)
        if self.after is not None and (type(self.after) is not StoryBibleRevisionHistoryPosition):
            raise TypeError("after must be a StoryBibleRevisionHistoryPosition or None")


@dataclass(frozen=True, slots=True)
class GetStoryBibleRevisionQuery:
    """Request one immutable Story Bible revision by sequence number."""

    story_bible_id: str
    revision_number: int

    def __post_init__(self) -> None:
        if type(self.story_bible_id) is not str:
            raise TypeError("story_bible_id must be a string")
        validate_story_bible_revision_number(self.revision_number)


__all__ = [
    "DEFAULT_STORY_BIBLE_REVISION_HISTORY_LIMIT",
    "MAX_STORY_BIBLE_REVISION_HISTORY_LIMIT",
    "GetStoryBibleRevisionQuery",
    "ListStoryBibleRevisionsQuery",
    "validate_story_bible_revision_history_limit",
    "validate_story_bible_revision_number",
]
