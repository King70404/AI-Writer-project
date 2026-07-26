"""Stable Project application read models made only from boundary-safe values."""

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.values import ProjectDescription, ProjectTitle


def _canonical_project_id(value: object) -> str:
    if type(value) is not str:
        raise TypeError("project_id must be a string")
    project_id = ProjectId.parse(value)
    canonical = str(project_id)
    if canonical != value:
        raise ValueError("project_id must use its canonical representation")
    return canonical


def _canonical_revision_id(value: object) -> str:
    if type(value) is not str:
        raise TypeError("current_revision_id must be a string")
    revision_id = ProjectRevisionId.parse(value)
    canonical = str(revision_id)
    if canonical != value:
        raise ValueError("current_revision_id must use its canonical representation")
    return canonical


def _canonical_history_revision_id(value: object) -> str:
    if type(value) is not str:
        raise TypeError("revision_id must be a string")
    revision_id = ProjectRevisionId.parse(value)
    canonical = str(revision_id)
    if canonical != value:
        raise ValueError("revision_id must use its canonical representation")
    return canonical


def _utc_datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    try:
        return ensure_utc(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be timezone-aware") from None


@dataclass(frozen=True, slots=True)
class ProjectListPosition:
    """Immutable keyset position for the last Project returned to a caller."""

    created_at: datetime
    project_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "created_at",
            _utc_datetime(self.created_at, field="created_at"),
        )
        object.__setattr__(self, "project_id", _canonical_project_id(self.project_id))


@dataclass(frozen=True, slots=True)
class ProjectListItem:
    """Detached current-revision summary returned by the Project list use case."""

    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime

    def __post_init__(self) -> None:
        project_id = _canonical_project_id(self.project_id)
        revision_id = _canonical_revision_id(self.current_revision_id)
        revision_number = int(RevisionNumber(self.revision_number))
        concurrency_version = int(ConcurrencyVersion(self.concurrency_version))
        if type(self.title) is not str:
            raise TypeError("title must be a string")
        title = str(ProjectTitle(self.title))
        created_at = _utc_datetime(self.created_at, field="created_at")
        updated_at = _utc_datetime(self.updated_at, field="updated_at")
        revision_created_at = _utc_datetime(
            self.revision_created_at,
            field="revision_created_at",
        )
        if updated_at < created_at or revision_created_at < created_at:
            raise ValueError("Project list item timestamps are inconsistent")
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "current_revision_id", revision_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "concurrency_version", concurrency_version)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "revision_created_at", revision_created_at)


@dataclass(frozen=True, slots=True)
class ProjectListPage:
    """One immutable keyset page without a count or transport cursor."""

    items: tuple[ProjectListItem, ...]
    next_position: ProjectListPosition | None
    has_more: bool

    def __post_init__(self) -> None:
        if type(self.items) is not tuple or any(
            type(item) is not ProjectListItem for item in self.items
        ):
            raise TypeError("items must be a tuple of ProjectListItem values")
        if type(self.has_more) is not bool:
            raise TypeError("has_more must be a bool")
        if self.next_position is not None and type(self.next_position) is not ProjectListPosition:
            raise TypeError("next_position must be a ProjectListPosition or None")
        positions = tuple(
            ProjectListPosition(created_at=item.created_at, project_id=item.project_id)
            for item in self.items
        )
        if any(
            (current.created_at, current.project_id) < (following.created_at, following.project_id)
            for current, following in pairwise(positions)
        ):
            raise ValueError("items must use descending Project list order")
        if self.has_more:
            if not positions or self.next_position != positions[-1]:
                raise ValueError("a continuing page requires its last item position")
        elif self.next_position is not None:
            raise ValueError("a final page cannot expose a next position")


@dataclass(frozen=True, slots=True)
class ProjectRevisionHistoryPosition:
    """Stable keyset position for the last returned Project revision."""

    project_id: str
    revision_number: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _canonical_project_id(self.project_id))
        object.__setattr__(
            self,
            "revision_number",
            int(RevisionNumber(self.revision_number)),
        )


@dataclass(frozen=True, slots=True)
class ProjectRevisionHistoryItem:
    """Detached summary for one immutable Project revision."""

    revision_id: str
    revision_number: int
    title: str
    created_at: datetime
    is_current: bool

    def __post_init__(self) -> None:
        if type(self.title) is not str:
            raise TypeError("title must be a string")
        if type(self.is_current) is not bool:
            raise TypeError("is_current must be a bool")
        object.__setattr__(
            self,
            "revision_id",
            _canonical_history_revision_id(self.revision_id),
        )
        object.__setattr__(
            self,
            "revision_number",
            int(RevisionNumber(self.revision_number)),
        )
        object.__setattr__(self, "title", str(ProjectTitle(self.title)))
        object.__setattr__(
            self,
            "created_at",
            _utc_datetime(self.created_at, field="created_at"),
        )


@dataclass(frozen=True, slots=True)
class ProjectRevisionHistoryPage:
    """One descending immutable revision page without a transport cursor."""

    project_id: str
    current_revision_number: int
    items: tuple[ProjectRevisionHistoryItem, ...]
    next_position: ProjectRevisionHistoryPosition | None
    has_more: bool

    def __post_init__(self) -> None:
        project_id = _canonical_project_id(self.project_id)
        current_revision_number = int(RevisionNumber(self.current_revision_number))
        if type(self.items) is not tuple or any(
            type(item) is not ProjectRevisionHistoryItem for item in self.items
        ):
            raise TypeError("items must be a tuple of ProjectRevisionHistoryItem values")
        if type(self.has_more) is not bool:
            raise TypeError("has_more must be a bool")
        if (
            self.next_position is not None
            and type(self.next_position) is not ProjectRevisionHistoryPosition
        ):
            raise TypeError("next_position must be a ProjectRevisionHistoryPosition or None")
        revision_numbers = tuple(item.revision_number for item in self.items)
        revision_ids = tuple(item.revision_id for item in self.items)
        if any(current <= following for current, following in pairwise(revision_numbers)):
            raise ValueError("items must use strictly descending RevisionNumber order")
        if len(set(revision_numbers)) != len(revision_numbers):
            raise ValueError("revision numbers must be unique within a page")
        if len(set(revision_ids)) != len(revision_ids):
            raise ValueError("revision identifiers must be unique within a page")
        current_items = tuple(item for item in self.items if item.is_current)
        if len(current_items) > 1 or any(
            item.revision_number != current_revision_number for item in current_items
        ):
            raise ValueError("current revision markers are inconsistent")
        if any(
            item.is_current != (item.revision_number == current_revision_number)
            for item in self.items
        ):
            raise ValueError("is_current must match current_revision_number")
        expected_position = (
            ProjectRevisionHistoryPosition(
                project_id=project_id,
                revision_number=self.items[-1].revision_number,
            )
            if self.items
            else None
        )
        if self.has_more:
            if expected_position is None or self.next_position != expected_position:
                raise ValueError("a continuing page requires its last item position")
        elif self.next_position is not None:
            raise ValueError("a final page cannot expose a next position")
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(
            self,
            "current_revision_number",
            current_revision_number,
        )


@dataclass(frozen=True, slots=True)
class ProjectRevisionHistorySnapshot:
    """Detached complete content for one immutable historical revision."""

    project_id: str
    revision_id: str
    revision_number: int
    title: str
    description: str
    created_at: datetime
    is_current: bool
    current_revision_number: int

    def __post_init__(self) -> None:
        if type(self.title) is not str:
            raise TypeError("title must be a string")
        if type(self.description) is not str:
            raise TypeError("description must be a string")
        if type(self.is_current) is not bool:
            raise TypeError("is_current must be a bool")
        project_id = _canonical_project_id(self.project_id)
        revision_id = _canonical_history_revision_id(self.revision_id)
        revision_number = int(RevisionNumber(self.revision_number))
        current_revision_number = int(RevisionNumber(self.current_revision_number))
        if self.is_current != (revision_number == current_revision_number):
            raise ValueError("is_current must match current_revision_number")
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "revision_id", revision_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "title", str(ProjectTitle(self.title)))
        object.__setattr__(
            self,
            "description",
            str(ProjectDescription(self.description)),
        )
        object.__setattr__(
            self,
            "created_at",
            _utc_datetime(self.created_at, field="created_at"),
        )
        object.__setattr__(
            self,
            "current_revision_number",
            current_revision_number,
        )


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    """Detached representation of one Project and its current immutable revision."""

    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime
    head_updated_at: datetime


__all__ = [
    "ProjectListItem",
    "ProjectListPage",
    "ProjectListPosition",
    "ProjectRevisionHistoryItem",
    "ProjectRevisionHistoryPage",
    "ProjectRevisionHistoryPosition",
    "ProjectRevisionHistorySnapshot",
    "ProjectSnapshot",
]
