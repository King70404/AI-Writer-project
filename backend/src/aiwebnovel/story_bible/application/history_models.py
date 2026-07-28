"""Immutable application read models for Story Bible revision history."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle


def _canonical_identifier(
    value: object,
    *,
    field: str,
    identifier_type: type[StoryBibleId] | type[StoryBibleRevisionId] | type[ProjectId],
) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be a string")
    try:
        canonical = str(identifier_type.parse(value))
    except DomainError:
        raise ValueError(f"{field} must be canonical") from None
    return canonical


def _positive_revision(value: object, *, field: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{field} must be a positive signed-64 integer")
    assert isinstance(value, int)
    try:
        return int(RevisionNumber(value))
    except (DomainError, TypeError, ValueError):
        raise ValueError(f"{field} must be a positive signed-64 integer") from None


def _aware_utc(value: object, *, field: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field} must be a datetime")
    try:
        normalized = ensure_utc(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an aware UTC datetime") from None
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must be UTC")
    return normalized


@dataclass(frozen=True, slots=True)
class StoryBibleRevisionHistoryPosition:
    """Story Bible-bound keyset position for one immutable revision page."""

    story_bible_id: StoryBibleId
    revision_number: RevisionNumber

    def __post_init__(self) -> None:
        if (
            type(self.story_bible_id) is not StoryBibleId
            or type(self.revision_number) is not RevisionNumber
        ):
            raise TypeError("history position requires StoryBibleId and RevisionNumber")


@dataclass(frozen=True, slots=True)
class StoryBibleRevisionHistoryItem:
    """Detached summary for one immutable Story Bible revision."""

    revision_id: str
    revision_number: int
    title: str
    created_at: datetime
    is_current: bool

    def __post_init__(self) -> None:
        revision_id = _canonical_identifier(
            self.revision_id,
            field="revision_id",
            identifier_type=StoryBibleRevisionId,
        )
        revision_number = _positive_revision(
            self.revision_number,
            field="revision_number",
        )
        if type(self.title) is not str:
            raise TypeError("title must be a string")
        title = str(StoryBibleTitle(self.title))
        if title != self.title:
            raise ValueError("title must be canonical")
        created_at = _aware_utc(self.created_at, field="created_at")
        if type(self.is_current) is not bool:
            raise TypeError("is_current must be a bool")
        object.__setattr__(self, "revision_id", revision_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "created_at", created_at)


@dataclass(frozen=True, slots=True)
class StoryBibleRevisionHistoryPage:
    """One descending immutable revision page without a transport cursor."""

    story_bible_id: str
    project_id: str
    current_revision_number: int
    items: tuple[StoryBibleRevisionHistoryItem, ...]
    next_position: StoryBibleRevisionHistoryPosition | None
    has_more: bool

    def __post_init__(self) -> None:
        story_bible_id = _canonical_identifier(
            self.story_bible_id,
            field="story_bible_id",
            identifier_type=StoryBibleId,
        )
        project_id = _canonical_identifier(
            self.project_id,
            field="project_id",
            identifier_type=ProjectId,
        )
        current_revision_number = _positive_revision(
            self.current_revision_number,
            field="current_revision_number",
        )
        if type(self.items) is not tuple or any(
            type(item) is not StoryBibleRevisionHistoryItem for item in self.items
        ):
            raise TypeError("items must be a tuple of StoryBibleRevisionHistoryItem values")
        if type(self.has_more) is not bool:
            raise TypeError("has_more must be a bool")
        if self.next_position is not None and (
            type(self.next_position) is not StoryBibleRevisionHistoryPosition
        ):
            raise TypeError("next_position must be a StoryBibleRevisionHistoryPosition or None")
        revision_numbers = tuple(item.revision_number for item in self.items)
        revision_ids = tuple(item.revision_id for item in self.items)
        if any(current <= following for current, following in pairwise(revision_numbers)):
            raise ValueError("items must use strictly descending RevisionNumber order")
        if len(set(revision_ids)) != len(revision_ids):
            raise ValueError("revision identifiers must be unique within a page")
        if sum(item.is_current for item in self.items) > 1 or any(
            item.is_current != (item.revision_number == current_revision_number)
            for item in self.items
        ):
            raise ValueError("current revision markers are inconsistent")
        expected_position = (
            StoryBibleRevisionHistoryPosition(
                story_bible_id=StoryBibleId.parse(story_bible_id),
                revision_number=RevisionNumber(self.items[-1].revision_number),
            )
            if self.items
            else None
        )
        if self.has_more:
            if expected_position is None or self.next_position != expected_position:
                raise ValueError("a continuing page requires its last item position")
        elif self.next_position is not None:
            raise ValueError("a final page cannot expose a next position")
        object.__setattr__(self, "story_bible_id", story_bible_id)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(
            self,
            "current_revision_number",
            current_revision_number,
        )


@dataclass(frozen=True, slots=True)
class StoryBibleRevisionSnapshot:
    """Detached complete content for one immutable Story Bible revision."""

    story_bible_id: str
    project_id: str
    revision_id: str
    revision_number: int
    title: str
    content: str
    created_at: datetime
    is_current: bool
    current_revision_number: int

    def __post_init__(self) -> None:
        story_bible_id = _canonical_identifier(
            self.story_bible_id,
            field="story_bible_id",
            identifier_type=StoryBibleId,
        )
        project_id = _canonical_identifier(
            self.project_id,
            field="project_id",
            identifier_type=ProjectId,
        )
        revision_id = _canonical_identifier(
            self.revision_id,
            field="revision_id",
            identifier_type=StoryBibleRevisionId,
        )
        revision_number = _positive_revision(
            self.revision_number,
            field="revision_number",
        )
        current_revision_number = _positive_revision(
            self.current_revision_number,
            field="current_revision_number",
        )
        if revision_number > current_revision_number:
            raise ValueError("revision_number cannot exceed current_revision_number")
        if type(self.is_current) is not bool:
            raise TypeError("is_current must be a bool")
        if self.is_current != (revision_number == current_revision_number):
            raise ValueError("is_current must match current_revision_number")
        if type(self.title) is not str:
            raise TypeError("title must be a string")
        title = str(StoryBibleTitle(self.title))
        if title != self.title:
            raise ValueError("title must be canonical")
        if type(self.content) is not str:
            raise TypeError("content must be a string")
        content = str(StoryBibleContent(self.content))
        if content != self.content:
            raise ValueError("content must be canonical")
        created_at = _aware_utc(self.created_at, field="created_at")
        object.__setattr__(self, "story_bible_id", story_bible_id)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "revision_id", revision_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(
            self,
            "current_revision_number",
            current_revision_number,
        )


__all__ = [
    "StoryBibleRevisionHistoryItem",
    "StoryBibleRevisionHistoryPage",
    "StoryBibleRevisionHistoryPosition",
    "StoryBibleRevisionSnapshot",
]
