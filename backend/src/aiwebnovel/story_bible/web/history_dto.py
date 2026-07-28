"""Strict immutable HTTP DTOs for Story Bible revision history."""

from datetime import datetime, timedelta
from itertools import pairwise
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle
from aiwebnovel.story_bible.web.history_cursor import (
    MAX_STORY_BIBLE_REVISION_CURSOR_LENGTH,
)

_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    strict=True,
    hide_input_in_errors=True,
)


def _canonical_id(
    value: str,
    identifier_type: type[StoryBibleId] | type[StoryBibleRevisionId] | type[ProjectId],
) -> str:
    try:
        canonical = str(identifier_type.parse(value))
    except DomainError:
        raise ValueError("identifier must be canonical") from None
    return canonical


def _revision_number(value: int) -> int:
    try:
        return int(RevisionNumber(value))
    except DomainError:
        raise ValueError("revision number must be positive") from None


def _utc_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be an aware UTC datetime")
    return value


class StoryBibleRevisionHistoryItemResponse(BaseModel):
    """Read-only summary for one immutable Story Bible revision."""

    model_config = _CONFIG

    revision_id: str
    revision_number: int
    title: str
    created_at: datetime
    is_current: bool

    @field_validator("revision_id")
    @classmethod
    def require_revision_id(cls, value: str) -> str:
        return _canonical_id(value, StoryBibleRevisionId)

    @field_validator("revision_number")
    @classmethod
    def require_revision_number(cls, value: int) -> int:
        return _revision_number(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        try:
            canonical = str(StoryBibleTitle(value))
        except DomainError:
            raise ValueError("title must satisfy Story Bible rules") from None
        if canonical != value:
            raise ValueError("title must be canonical")
        return value

    @field_validator("created_at")
    @classmethod
    def require_created_at(cls, value: datetime) -> datetime:
        return _utc_time(value)


class StoryBibleRevisionHistoryPageResponse(BaseModel):
    """One immutable keyset page without content or a total count."""

    model_config = _CONFIG

    story_bible_id: str
    project_id: str
    current_revision_number: int
    items: tuple[StoryBibleRevisionHistoryItemResponse, ...]
    next_cursor: str | None
    has_more: bool

    @field_validator("story_bible_id")
    @classmethod
    def require_story_bible_id(cls, value: str) -> str:
        return _canonical_id(value, StoryBibleId)

    @field_validator("project_id")
    @classmethod
    def require_project_id(cls, value: str) -> str:
        return _canonical_id(value, ProjectId)

    @field_validator("current_revision_number")
    @classmethod
    def require_current_revision_number(cls, value: int) -> int:
        return _revision_number(value)

    @field_validator("next_cursor")
    @classmethod
    def require_cursor_shape(cls, value: str | None) -> str | None:
        if value is not None and (
            not value or len(value) > MAX_STORY_BIBLE_REVISION_CURSOR_LENGTH or not value.isascii()
        ):
            raise ValueError("next_cursor must be an opaque bounded string")
        return value

    @model_validator(mode="after")
    def require_consistent_page(self) -> Self:
        numbers = tuple(item.revision_number for item in self.items)
        identifiers = tuple(item.revision_id for item in self.items)
        if any(current <= following for current, following in pairwise(numbers)):
            raise ValueError("history items must be strictly descending")
        if len(set(numbers)) != len(numbers) or len(set(identifiers)) != len(identifiers):
            raise ValueError("history items must be unique")
        if sum(item.is_current for item in self.items) > 1 or any(
            item.is_current != (item.revision_number == self.current_revision_number)
            for item in self.items
        ):
            raise ValueError("current revision markers are inconsistent")
        if self.has_more != (self.next_cursor is not None):
            raise ValueError("has_more and next_cursor are inconsistent")
        if not self.items and (self.has_more or self.next_cursor is not None):
            raise ValueError("an empty page cannot continue")
        return self


class StoryBibleRevisionResponse(BaseModel):
    """Complete read-only content for one immutable Story Bible revision."""

    model_config = _CONFIG

    story_bible_id: str
    project_id: str
    revision_id: str
    revision_number: int
    title: str
    content: str
    created_at: datetime
    is_current: bool
    current_revision_number: int

    @field_validator("story_bible_id")
    @classmethod
    def require_story_bible_id(cls, value: str) -> str:
        return _canonical_id(value, StoryBibleId)

    @field_validator("project_id")
    @classmethod
    def require_project_id(cls, value: str) -> str:
        return _canonical_id(value, ProjectId)

    @field_validator("revision_id")
    @classmethod
    def require_revision_id(cls, value: str) -> str:
        return _canonical_id(value, StoryBibleRevisionId)

    @field_validator("revision_number", "current_revision_number")
    @classmethod
    def require_revision_number(cls, value: int) -> int:
        return _revision_number(value)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        try:
            canonical = str(StoryBibleTitle(value))
        except DomainError:
            raise ValueError("title must satisfy Story Bible rules") from None
        if canonical != value:
            raise ValueError("title must be canonical")
        return value

    @field_validator("content")
    @classmethod
    def require_content(cls, value: str) -> str:
        try:
            canonical = str(StoryBibleContent(value))
        except DomainError:
            raise ValueError("content must satisfy Story Bible rules") from None
        if canonical != value:
            raise ValueError("content must be canonical")
        return value

    @field_validator("created_at")
    @classmethod
    def require_created_at(cls, value: datetime) -> datetime:
        return _utc_time(value)

    @model_validator(mode="after")
    def require_consistent_revision(self) -> Self:
        if self.revision_number > self.current_revision_number:
            raise ValueError("revision cannot exceed the current revision")
        if self.is_current != (self.revision_number == self.current_revision_number):
            raise ValueError("is_current must match current_revision_number")
        return self


__all__ = [
    "StoryBibleRevisionHistoryItemResponse",
    "StoryBibleRevisionHistoryPageResponse",
    "StoryBibleRevisionResponse",
]
