"""Strict immutable HTTP DTOs for Character revision history."""

from datetime import datetime, timedelta
from itertools import pairwise
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.character.web.history_cursor import MAX_CHARACTER_REVISION_CURSOR_LENGTH
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId

_CONFIG = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


def _canonical_id(
    value: str,
    identifier_type: type[CharacterId] | type[CharacterRevisionId] | type[ProjectId],
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


def _name(value: str) -> str:
    try:
        canonical = str(CharacterName(value))
    except DomainError:
        raise ValueError("name must satisfy Character rules") from None
    if canonical != value:
        raise ValueError("name must be canonical")
    return value


def _role(value: str) -> str:
    try:
        canonical = str(CharacterRole(value))
    except DomainError:
        raise ValueError("role must satisfy Character rules") from None
    if canonical != value:
        raise ValueError("role must be canonical")
    return value


class CharacterRevisionHistoryItemResponse(BaseModel):
    model_config = _CONFIG

    revision_id: str
    revision_number: int
    name: str
    role: str
    created_at: datetime
    is_current: bool

    @field_validator("revision_id")
    @classmethod
    def require_revision_id(cls, value: str) -> str:
        return _canonical_id(value, CharacterRevisionId)

    @field_validator("revision_number")
    @classmethod
    def require_revision_number(cls, value: int) -> int:
        return _revision_number(value)

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        return _name(value)

    @field_validator("role")
    @classmethod
    def require_role(cls, value: str) -> str:
        return _role(value)

    @field_validator("created_at")
    @classmethod
    def require_created_at(cls, value: datetime) -> datetime:
        return _utc_time(value)


class CharacterRevisionHistoryPageResponse(BaseModel):
    model_config = _CONFIG

    character_id: str
    project_id: str
    current_revision_number: int
    items: tuple[CharacterRevisionHistoryItemResponse, ...]
    next_cursor: str | None
    has_more: bool

    @field_validator("character_id")
    @classmethod
    def require_character_id(cls, value: str) -> str:
        return _canonical_id(value, CharacterId)

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
            not value or len(value) > MAX_CHARACTER_REVISION_CURSOR_LENGTH or not value.isascii()
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
        if not self.items and self.has_more:
            raise ValueError("an empty page cannot continue")
        return self


class CharacterRevisionResponse(BaseModel):
    model_config = _CONFIG

    character_id: str
    project_id: str
    revision_id: str
    revision_number: int
    name: str
    role: str
    profile: str
    created_at: datetime
    is_current: bool
    current_revision_number: int

    @field_validator("character_id")
    @classmethod
    def require_character_id(cls, value: str) -> str:
        return _canonical_id(value, CharacterId)

    @field_validator("project_id")
    @classmethod
    def require_project_id(cls, value: str) -> str:
        return _canonical_id(value, ProjectId)

    @field_validator("revision_id")
    @classmethod
    def require_revision_id(cls, value: str) -> str:
        return _canonical_id(value, CharacterRevisionId)

    @field_validator("revision_number", "current_revision_number")
    @classmethod
    def require_revision_number(cls, value: int) -> int:
        return _revision_number(value)

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        return _name(value)

    @field_validator("role")
    @classmethod
    def require_role(cls, value: str) -> str:
        return _role(value)

    @field_validator("profile")
    @classmethod
    def require_profile(cls, value: str) -> str:
        try:
            canonical = str(CharacterProfile(value))
        except DomainError:
            raise ValueError("profile must satisfy Character rules") from None
        if canonical != value:
            raise ValueError("profile must be canonical")
        return value

    @field_validator("created_at")
    @classmethod
    def require_created_at(cls, value: datetime) -> datetime:
        return _utc_time(value)

    @model_validator(mode="after")
    def require_consistent_revision(self) -> Self:
        if self.is_current != (self.revision_number == self.current_revision_number):
            raise ValueError("is_current must match current_revision_number")
        return self


__all__ = [
    "CharacterRevisionHistoryItemResponse",
    "CharacterRevisionHistoryPageResponse",
    "CharacterRevisionResponse",
]
