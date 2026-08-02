"""Immutable application read models for Character revision history."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.identifiers import ProjectId


def _canonical_identifier(
    value: object,
    *,
    field: str,
    identifier_type: type[CharacterId] | type[CharacterRevisionId] | type[ProjectId],
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


def _canonical_summary_text(name: object, role: object) -> tuple[str, str]:
    if type(name) is not str or type(role) is not str:
        raise TypeError("name and role must be strings")
    canonical_name = str(CharacterName(name))
    canonical_role = str(CharacterRole(role))
    if canonical_name != name or canonical_role != role:
        raise ValueError("name and role must be canonical")
    return canonical_name, canonical_role


@dataclass(frozen=True, slots=True)
class CharacterRevisionHistoryPosition:
    """Character-bound keyset position for one immutable revision page."""

    character_id: CharacterId
    revision_number: RevisionNumber

    def __post_init__(self) -> None:
        if (
            type(self.character_id) is not CharacterId
            or type(self.revision_number) is not RevisionNumber
        ):
            raise TypeError("history position requires CharacterId and RevisionNumber")


@dataclass(frozen=True, slots=True)
class CharacterRevisionHistoryItem:
    """Detached summary for one immutable Character revision."""

    revision_id: str
    revision_number: int
    name: str
    role: str
    created_at: datetime
    is_current: bool

    def __post_init__(self) -> None:
        revision_id = _canonical_identifier(
            self.revision_id,
            field="revision_id",
            identifier_type=CharacterRevisionId,
        )
        revision_number = _positive_revision(self.revision_number, field="revision_number")
        name, role = _canonical_summary_text(self.name, self.role)
        created_at = _aware_utc(self.created_at, field="created_at")
        if type(self.is_current) is not bool:
            raise TypeError("is_current must be a bool")
        object.__setattr__(self, "revision_id", revision_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "created_at", created_at)


@dataclass(frozen=True, slots=True)
class CharacterRevisionHistoryPage:
    """One descending immutable revision page without a transport cursor."""

    character_id: str
    project_id: str
    current_revision_number: int
    items: tuple[CharacterRevisionHistoryItem, ...]
    next_position: CharacterRevisionHistoryPosition | None
    has_more: bool

    def __post_init__(self) -> None:
        character_id = _canonical_identifier(
            self.character_id,
            field="character_id",
            identifier_type=CharacterId,
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
            type(item) is not CharacterRevisionHistoryItem for item in self.items
        ):
            raise TypeError("items must be a tuple of CharacterRevisionHistoryItem values")
        if type(self.has_more) is not bool:
            raise TypeError("has_more must be a bool")
        if (
            self.next_position is not None
            and type(self.next_position) is not CharacterRevisionHistoryPosition
        ):
            raise TypeError("next_position must be a CharacterRevisionHistoryPosition or None")
        revision_numbers = tuple(item.revision_number for item in self.items)
        revision_ids = tuple(item.revision_id for item in self.items)
        if any(current <= following for current, following in pairwise(revision_numbers)):
            raise ValueError("items must use strictly descending RevisionNumber order")
        if len(set(revision_numbers)) != len(revision_numbers) or len(set(revision_ids)) != len(
            revision_ids
        ):
            raise ValueError("revision identifiers and numbers must be unique within a page")
        if sum(item.is_current for item in self.items) > 1 or any(
            item.is_current != (item.revision_number == current_revision_number)
            for item in self.items
        ):
            raise ValueError("current revision markers are inconsistent")
        expected_position = (
            CharacterRevisionHistoryPosition(
                character_id=CharacterId.parse(character_id),
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
        object.__setattr__(self, "character_id", character_id)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "current_revision_number", current_revision_number)


@dataclass(frozen=True, slots=True)
class CharacterRevisionSnapshot:
    """Detached complete content for one immutable Character revision."""

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

    def __post_init__(self) -> None:
        character_id = _canonical_identifier(
            self.character_id,
            field="character_id",
            identifier_type=CharacterId,
        )
        project_id = _canonical_identifier(
            self.project_id, field="project_id", identifier_type=ProjectId
        )
        revision_id = _canonical_identifier(
            self.revision_id,
            field="revision_id",
            identifier_type=CharacterRevisionId,
        )
        revision_number = _positive_revision(self.revision_number, field="revision_number")
        current_revision_number = _positive_revision(
            self.current_revision_number,
            field="current_revision_number",
        )
        if type(self.is_current) is not bool:
            raise TypeError("is_current must be a bool")
        if self.is_current != (revision_number == current_revision_number):
            raise ValueError("is_current must match current_revision_number")
        name, role = _canonical_summary_text(self.name, self.role)
        if type(self.profile) is not str:
            raise TypeError("profile must be a string")
        profile = str(CharacterProfile(self.profile))
        if profile != self.profile:
            raise ValueError("profile must be canonical")
        created_at = _aware_utc(self.created_at, field="created_at")
        object.__setattr__(self, "character_id", character_id)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "revision_id", revision_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "current_revision_number", current_revision_number)


__all__ = [
    "CharacterRevisionHistoryItem",
    "CharacterRevisionHistoryPage",
    "CharacterRevisionHistoryPosition",
    "CharacterRevisionSnapshot",
]
