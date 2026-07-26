"""Immutable raw inputs for Project read use cases."""

from dataclasses import dataclass

from aiwebnovel.project.application.models import (
    ProjectListPosition,
    ProjectRevisionHistoryPosition,
)

DEFAULT_PROJECT_LIST_LIMIT = 20
MAX_PROJECT_LIST_LIMIT = 100
DEFAULT_PROJECT_REVISION_HISTORY_LIMIT = 20
MAX_PROJECT_REVISION_HISTORY_LIMIT = 100


def validate_project_list_limit(limit: object) -> int:
    """Return a valid bounded list limit without coercing bools or numbers."""
    if type(limit) is not int or not 1 <= limit <= MAX_PROJECT_LIST_LIMIT:
        raise ValueError("limit must be an integer from 1 through 100")
    return limit


def validate_project_revision_history_limit(limit: object) -> int:
    """Return a valid history limit without coercing bools or numbers."""
    if type(limit) is not int or not 1 <= limit <= MAX_PROJECT_REVISION_HISTORY_LIMIT:
        raise ValueError("limit must be an integer from 1 through 100")
    return limit


@dataclass(frozen=True, slots=True)
class ListProjectsQuery:
    """Request one stable Project keyset page."""

    limit: int = DEFAULT_PROJECT_LIST_LIMIT
    after: ProjectListPosition | None = None

    def __post_init__(self) -> None:
        validate_project_list_limit(self.limit)
        if self.after is not None and type(self.after) is not ProjectListPosition:
            raise TypeError("after must be a ProjectListPosition or None")


@dataclass(frozen=True, slots=True)
class GetProjectQuery:
    """Request the current snapshot for one externally represented Project ID."""

    project_id: str


@dataclass(frozen=True, slots=True)
class ListProjectRevisionsQuery:
    """Request one descending immutable revision-history page."""

    project_id: str
    limit: int = DEFAULT_PROJECT_REVISION_HISTORY_LIMIT
    after: ProjectRevisionHistoryPosition | None = None

    def __post_init__(self) -> None:
        validate_project_revision_history_limit(self.limit)
        if self.after is not None and type(self.after) is not ProjectRevisionHistoryPosition:
            raise TypeError("after must be a ProjectRevisionHistoryPosition or None")


@dataclass(frozen=True, slots=True)
class GetProjectRevisionQuery:
    """Request one immutable Project revision by its stable sequence number."""

    project_id: str
    revision_number: int


__all__ = [
    "DEFAULT_PROJECT_LIST_LIMIT",
    "DEFAULT_PROJECT_REVISION_HISTORY_LIMIT",
    "MAX_PROJECT_LIST_LIMIT",
    "MAX_PROJECT_REVISION_HISTORY_LIMIT",
    "GetProjectQuery",
    "GetProjectRevisionQuery",
    "ListProjectRevisionsQuery",
    "ListProjectsQuery",
    "validate_project_list_limit",
    "validate_project_revision_history_limit",
]
