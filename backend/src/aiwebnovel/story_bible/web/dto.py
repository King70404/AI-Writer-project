"""Strict immutable HTTP DTOs for the Story Bible API."""

from datetime import datetime, timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle


class CreateStoryBibleRequest(BaseModel):
    """Client-owned fields accepted for an initial Story Bible."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    title: str
    content: str = ""


class ReviseStoryBibleRequest(BaseModel):
    """Complete client-owned replacement accepted for a Story Bible revision."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    title: str
    content: str


class StoryBibleResponse(BaseModel):
    """Detached current Story Bible state exposed over HTTP."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    story_bible_id: str
    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime
    head_updated_at: datetime

    @field_validator("story_bible_id")
    @classmethod
    def require_story_bible_id(cls, value: str) -> str:
        try:
            StoryBibleId.parse(value)
        except DomainError:
            raise ValueError("story_bible_id must be canonical") from None
        return value

    @field_validator("project_id")
    @classmethod
    def require_project_id(cls, value: str) -> str:
        try:
            ProjectId.parse(value)
        except DomainError:
            raise ValueError("project_id must be canonical") from None
        return value

    @field_validator("current_revision_id")
    @classmethod
    def require_revision_id(cls, value: str) -> str:
        try:
            StoryBibleRevisionId.parse(value)
        except DomainError:
            raise ValueError("current_revision_id must be canonical") from None
        return value

    @field_validator("revision_number")
    @classmethod
    def require_revision_number(cls, value: int) -> int:
        try:
            return int(RevisionNumber(value))
        except DomainError:
            raise ValueError("revision_number must be positive") from None

    @field_validator("concurrency_version")
    @classmethod
    def require_concurrency_version(cls, value: int) -> int:
        try:
            return int(ConcurrencyVersion(value))
        except DomainError:
            raise ValueError("concurrency_version must be positive") from None

    @field_validator("title")
    @classmethod
    def require_canonical_title(cls, value: str) -> str:
        try:
            normalized = str(StoryBibleTitle(value))
        except DomainError:
            raise ValueError("title must satisfy Story Bible rules") from None
        if normalized != value:
            raise ValueError("title must be canonical")
        return value

    @field_validator("content")
    @classmethod
    def require_canonical_content(cls, value: str) -> str:
        try:
            normalized = str(StoryBibleContent(value))
        except DomainError:
            raise ValueError("content must satisfy Story Bible rules") from None
        if normalized != value:
            raise ValueError("content must be canonical")
        return value

    @field_validator(
        "created_at",
        "updated_at",
        "revision_created_at",
        "head_updated_at",
    )
    @classmethod
    def require_utc_datetime(cls, value: datetime) -> datetime:
        try:
            normalized = ensure_utc(value)
        except (TypeError, ValueError):
            raise ValueError("Story Bible response timestamps must be aware UTC") from None
        if value.utcoffset() != timedelta(0):
            raise ValueError("Story Bible response timestamps must be UTC")
        return normalized

    @model_validator(mode="after")
    def require_consistent_state(self) -> Self:
        if self.revision_number != self.concurrency_version:
            raise ValueError("Story Bible response versions must match")
        if (
            self.created_at > self.updated_at
            or self.updated_at != self.revision_created_at
            or self.updated_at != self.head_updated_at
        ):
            raise ValueError("Story Bible response timestamps are inconsistent")
        return self


__all__ = [
    "CreateStoryBibleRequest",
    "ReviseStoryBibleRequest",
    "StoryBibleResponse",
]
