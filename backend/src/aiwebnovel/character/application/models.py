"""Detached Character application read models with strict invariants."""

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
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
    parsed = identifier_type.parse(value)
    return str(parsed)


def _positive_revision_number(value: object) -> int:
    if type(value) is not int:
        raise TypeError("revision_number must be an integer")
    return int(RevisionNumber(value))


def _positive_concurrency_version(value: object) -> int:
    if type(value) is not int:
        raise TypeError("concurrency_version must be an integer")
    return int(ConcurrencyVersion(value))


def _utc_datetime(value: object, *, field: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field} must be a datetime")
    try:
        return ensure_utc(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be timezone-aware") from None


@dataclass(frozen=True, slots=True)
class CharacterListPosition:
    """Project-bound composite keyset position for a Character page."""

    project_id: ProjectId
    created_at: datetime
    character_id: CharacterId

    def __post_init__(self) -> None:
        if type(self.project_id) is not ProjectId:
            raise TypeError("project_id must be a ProjectId")
        if type(self.character_id) is not CharacterId:
            raise TypeError("character_id must be a CharacterId")
        object.__setattr__(
            self,
            "created_at",
            _utc_datetime(self.created_at, field="created_at"),
        )


@dataclass(frozen=True, slots=True)
class CharacterSnapshot:
    """Complete current Character state detached from domain and persistence."""

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
        revision_id = _canonical_identifier(
            self.current_revision_id,
            field="current_revision_id",
            identifier_type=CharacterRevisionId,
        )
        revision_number = _positive_revision_number(self.revision_number)
        concurrency_version = _positive_concurrency_version(self.concurrency_version)
        if revision_number != concurrency_version:
            raise ValueError("revision and concurrency versions must match")
        if type(self.name) is not str:
            raise TypeError("name must be a string")
        if type(self.role) is not str:
            raise TypeError("role must be a string")
        if type(self.profile) is not str:
            raise TypeError("profile must be a string")
        name = str(CharacterName(self.name))
        role = str(CharacterRole(self.role))
        profile = str(CharacterProfile(self.profile))
        created_at = _utc_datetime(self.created_at, field="created_at")
        updated_at = _utc_datetime(self.updated_at, field="updated_at")
        revision_created_at = _utc_datetime(
            self.revision_created_at,
            field="revision_created_at",
        )
        head_updated_at = _utc_datetime(
            self.head_updated_at,
            field="head_updated_at",
        )
        if (
            created_at > updated_at
            or updated_at != revision_created_at
            or updated_at != head_updated_at
        ):
            raise ValueError("Character snapshot timestamps are inconsistent")
        object.__setattr__(self, "character_id", character_id)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "current_revision_id", revision_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "concurrency_version", concurrency_version)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "revision_created_at", revision_created_at)
        object.__setattr__(self, "head_updated_at", head_updated_at)


@dataclass(frozen=True, slots=True)
class CharacterListItem:
    """Detached current Character summary that intentionally omits profile."""

    character_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    name: str
    role: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        character_id = _canonical_identifier(
            self.character_id,
            field="character_id",
            identifier_type=CharacterId,
        )
        revision_id = _canonical_identifier(
            self.current_revision_id,
            field="current_revision_id",
            identifier_type=CharacterRevisionId,
        )
        revision_number = _positive_revision_number(self.revision_number)
        concurrency_version = _positive_concurrency_version(self.concurrency_version)
        if revision_number != concurrency_version:
            raise ValueError("revision and concurrency versions must match")
        if type(self.name) is not str:
            raise TypeError("name must be a string")
        if type(self.role) is not str:
            raise TypeError("role must be a string")
        name = str(CharacterName(self.name))
        role = str(CharacterRole(self.role))
        created_at = _utc_datetime(self.created_at, field="created_at")
        updated_at = _utc_datetime(self.updated_at, field="updated_at")
        if created_at > updated_at:
            raise ValueError("Character list item timestamps are inconsistent")
        object.__setattr__(self, "character_id", character_id)
        object.__setattr__(self, "current_revision_id", revision_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "concurrency_version", concurrency_version)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


@dataclass(frozen=True, slots=True)
class CharacterListPage:
    """One immutable Project-bound page without total or cursor text."""

    project_id: str
    items: tuple[CharacterListItem, ...]
    next_position: CharacterListPosition | None
    has_more: bool

    def __post_init__(self) -> None:
        project_id = _canonical_identifier(
            self.project_id,
            field="project_id",
            identifier_type=ProjectId,
        )
        parsed_project_id = ProjectId.parse(project_id)
        if type(self.items) is not tuple or any(
            type(item) is not CharacterListItem for item in self.items
        ):
            raise TypeError("items must be a tuple of CharacterListItem values")
        if type(self.has_more) is not bool:
            raise TypeError("has_more must be a bool")
        if self.next_position is not None and type(self.next_position) is not CharacterListPosition:
            raise TypeError("next_position must be a CharacterListPosition or None")
        character_ids = tuple(item.character_id for item in self.items)
        if len(set(character_ids)) != len(character_ids):
            raise ValueError("Character identifiers must be unique within a page")
        positions = tuple((item.created_at, item.character_id) for item in self.items)
        if any(current <= following for current, following in pairwise(positions)):
            raise ValueError("items must use strict descending Character list order")
        expected_position = (
            CharacterListPosition(
                project_id=parsed_project_id,
                created_at=self.items[-1].created_at,
                character_id=CharacterId.parse(self.items[-1].character_id),
            )
            if self.items
            else None
        )
        if self.next_position is not None and self.next_position.project_id != parsed_project_id:
            raise ValueError("next_position must belong to the requested Project")
        if self.has_more:
            if expected_position is None or self.next_position != expected_position:
                raise ValueError("a continuing page requires its last item position")
        elif self.next_position is not None:
            raise ValueError("a final page cannot expose a next position")
        object.__setattr__(self, "project_id", project_id)


__all__ = [
    "CharacterListItem",
    "CharacterListPage",
    "CharacterListPosition",
    "CharacterSnapshot",
]
