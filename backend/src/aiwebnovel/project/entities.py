"""Immutable Project domain entities and aggregate invariants."""

from dataclasses import dataclass
from datetime import datetime

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.errors import InvalidProjectState
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.values import ProjectDescription, ProjectTitle


def _project_time(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise InvalidProjectState
    try:
        return ensure_utc(value)
    except (TypeError, ValueError):
        raise InvalidProjectState from None


@dataclass(frozen=True, slots=True)
class Project:
    """Stable Project identity and optimistic-concurrency anchor."""

    id: ProjectId
    concurrency_version: ConcurrencyVersion
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not ProjectId
            or type(self.concurrency_version) is not ConcurrencyVersion
        ):
            raise InvalidProjectState
        created_at = _project_time(self.created_at)
        updated_at = _project_time(self.updated_at)
        if updated_at < created_at:
            raise InvalidProjectState
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


@dataclass(frozen=True, slots=True)
class ProjectRevision:
    """One immutable content revision belonging to a stable Project."""

    id: ProjectRevisionId
    project_id: ProjectId
    revision_number: RevisionNumber
    title: ProjectTitle
    description: ProjectDescription
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not ProjectRevisionId
            or type(self.project_id) is not ProjectId
            or type(self.revision_number) is not RevisionNumber
            or type(self.title) is not ProjectTitle
            or type(self.description) is not ProjectDescription
        ):
            raise InvalidProjectState
        object.__setattr__(self, "created_at", _project_time(self.created_at))


@dataclass(frozen=True, slots=True)
class ProjectHead:
    """The replaceable pointer to one Project's current immutable revision."""

    project_id: ProjectId
    revision_id: ProjectRevisionId
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.project_id) is not ProjectId
            or type(self.revision_id) is not ProjectRevisionId
        ):
            raise InvalidProjectState
        object.__setattr__(self, "updated_at", _project_time(self.updated_at))


@dataclass(frozen=True, slots=True)
class ProjectAggregate:
    """A read-only consistent view of a Project and its current revision."""

    project: Project
    head: ProjectHead
    current_revision: ProjectRevision

    def __post_init__(self) -> None:
        if (
            type(self.project) is not Project
            or type(self.head) is not ProjectHead
            or type(self.current_revision) is not ProjectRevision
            or self.head.project_id != self.project.id
            or self.current_revision.project_id != self.project.id
            or self.head.revision_id != self.current_revision.id
            or self.project.updated_at < self.project.created_at
            or self.head.updated_at < self.current_revision.created_at
            or int(self.current_revision.revision_number) < 1
        ):
            raise InvalidProjectState
