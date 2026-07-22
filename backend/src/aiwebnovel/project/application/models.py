"""Stable Project application read models made only from boundary-safe values."""

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.values import ProjectTitle


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
    "ProjectSnapshot",
]
