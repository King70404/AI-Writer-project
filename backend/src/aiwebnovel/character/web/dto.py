"""Strict immutable HTTP DTOs for current Character resources and lists."""

from datetime import datetime, timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.identifiers import ProjectId


class _StrictCharacterModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class CreateCharacterRequest(_StrictCharacterModel):
    """Client-owned fields accepted for an initial Character."""

    name: str
    role: str = ""
    profile: str = ""


class ReviseCharacterRequest(_StrictCharacterModel):
    """Complete client-owned replacement accepted for a Character revision."""

    name: str
    role: str
    profile: str


def _require_character_id(value: str) -> str:
    try:
        CharacterId.parse(value)
    except DomainError:
        raise ValueError("character_id must be canonical") from None
    return value


def _require_revision_id(value: str) -> str:
    try:
        CharacterRevisionId.parse(value)
    except DomainError:
        raise ValueError("current_revision_id must be canonical") from None
    return value


def _require_project_id(value: str) -> str:
    try:
        ProjectId.parse(value)
    except DomainError:
        raise ValueError("project_id must be canonical") from None
    return value


def _require_revision_number(value: int) -> int:
    try:
        return int(RevisionNumber(value))
    except DomainError:
        raise ValueError("revision_number must be positive") from None


def _require_concurrency_version(value: int) -> int:
    try:
        return int(ConcurrencyVersion(value))
    except DomainError:
        raise ValueError("concurrency_version must be positive") from None


def _require_name(value: str) -> str:
    try:
        normalized = str(CharacterName(value))
    except DomainError:
        raise ValueError("name must satisfy Character rules") from None
    if normalized != value:
        raise ValueError("name must be canonical")
    return value


def _require_role(value: str) -> str:
    try:
        normalized = str(CharacterRole(value))
    except DomainError:
        raise ValueError("role must satisfy Character rules") from None
    if normalized != value:
        raise ValueError("role must be canonical")
    return value


def _require_profile(value: str) -> str:
    try:
        normalized = str(CharacterProfile(value))
    except DomainError:
        raise ValueError("profile must satisfy Character rules") from None
    if normalized != value:
        raise ValueError("profile must be canonical")
    return value


def _require_utc(value: datetime) -> datetime:
    try:
        normalized = ensure_utc(value)
    except (TypeError, ValueError):
        raise ValueError("Character response timestamps must be aware UTC") from None
    if value.utcoffset() != timedelta(0):
        raise ValueError("Character response timestamps must be UTC")
    return normalized


class CharacterResponse(_StrictCharacterModel):
    """Detached complete current Character state exposed over HTTP."""

    character_id: str
    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    name: str
    role: str
    profile: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime
    head_updated_at: datetime

    _character_id = field_validator("character_id")(_require_character_id)
    _project_id = field_validator("project_id")(_require_project_id)
    _revision_id = field_validator("current_revision_id")(_require_revision_id)
    _revision_number = field_validator("revision_number")(_require_revision_number)
    _concurrency_version = field_validator("concurrency_version")(_require_concurrency_version)
    _name = field_validator("name")(_require_name)
    _role = field_validator("role")(_require_role)
    _profile = field_validator("profile")(_require_profile)
    _timestamps = field_validator(
        "created_at",
        "updated_at",
        "revision_created_at",
        "head_updated_at",
    )(_require_utc)

    @model_validator(mode="after")
    def require_consistent_state(self) -> Self:
        if self.revision_number != self.concurrency_version:
            raise ValueError("Character response versions must match")
        if (
            self.created_at > self.updated_at
            or self.updated_at != self.revision_created_at
            or self.updated_at != self.head_updated_at
        ):
            raise ValueError("Character response timestamps are inconsistent")
        return self


class CharacterListItemResponse(_StrictCharacterModel):
    """Current Character summary that intentionally omits profile."""

    character_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    name: str
    role: str
    created_at: datetime
    updated_at: datetime

    _character_id = field_validator("character_id")(_require_character_id)
    _revision_id = field_validator("current_revision_id")(_require_revision_id)
    _revision_number = field_validator("revision_number")(_require_revision_number)
    _concurrency_version = field_validator("concurrency_version")(_require_concurrency_version)
    _name = field_validator("name")(_require_name)
    _role = field_validator("role")(_require_role)
    _timestamps = field_validator("created_at", "updated_at")(_require_utc)

    @model_validator(mode="after")
    def require_consistent_state(self) -> Self:
        if self.revision_number != self.concurrency_version:
            raise ValueError("Character list item versions must match")
        if self.created_at > self.updated_at:
            raise ValueError("Character list item timestamps are inconsistent")
        return self


class CharacterListPageResponse(_StrictCharacterModel):
    """One Project-bound Character page without profile or total."""

    project_id: str
    items: tuple[CharacterListItemResponse, ...]
    next_cursor: str | None
    has_more: bool

    _project_id = field_validator("project_id")(_require_project_id)

    @model_validator(mode="after")
    def require_cursor_consistency(self) -> Self:
        if self.has_more:
            if not self.next_cursor:
                raise ValueError("a continuing Character page requires a cursor")
        elif self.next_cursor is not None:
            raise ValueError("a final Character page cannot expose a cursor")
        return self


__all__ = [
    "CharacterListItemResponse",
    "CharacterListPageResponse",
    "CharacterResponse",
    "CreateCharacterRequest",
    "ReviseCharacterRequest",
]
