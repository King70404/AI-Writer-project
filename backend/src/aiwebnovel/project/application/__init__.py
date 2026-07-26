"""Framework-independent Project application use cases and read models."""

from aiwebnovel.project.application.commands import (
    CreateProjectCommand,
    ReviseProjectCommand,
)
from aiwebnovel.project.application.history import ProjectRevisionHistoryReader
from aiwebnovel.project.application.listing import ProjectListReader
from aiwebnovel.project.application.models import (
    ProjectListItem,
    ProjectListPage,
    ProjectListPosition,
    ProjectRevisionHistoryItem,
    ProjectRevisionHistoryPage,
    ProjectRevisionHistoryPosition,
    ProjectRevisionHistorySnapshot,
    ProjectSnapshot,
)
from aiwebnovel.project.application.queries import (
    DEFAULT_PROJECT_LIST_LIMIT,
    DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
    MAX_PROJECT_LIST_LIMIT,
    MAX_PROJECT_REVISION_HISTORY_LIMIT,
    GetProjectQuery,
    GetProjectRevisionQuery,
    ListProjectRevisionsQuery,
    ListProjectsQuery,
)
from aiwebnovel.project.application.services import (
    ProjectCommandService,
    ProjectListQueryService,
    ProjectQueryService,
    ProjectRevisionHistoryQueryService,
)

__all__ = [
    "DEFAULT_PROJECT_LIST_LIMIT",
    "DEFAULT_PROJECT_REVISION_HISTORY_LIMIT",
    "MAX_PROJECT_LIST_LIMIT",
    "MAX_PROJECT_REVISION_HISTORY_LIMIT",
    "CreateProjectCommand",
    "GetProjectQuery",
    "GetProjectRevisionQuery",
    "ListProjectRevisionsQuery",
    "ListProjectsQuery",
    "ProjectCommandService",
    "ProjectListItem",
    "ProjectListPage",
    "ProjectListPosition",
    "ProjectListQueryService",
    "ProjectListReader",
    "ProjectQueryService",
    "ProjectRevisionHistoryItem",
    "ProjectRevisionHistoryPage",
    "ProjectRevisionHistoryPosition",
    "ProjectRevisionHistoryQueryService",
    "ProjectRevisionHistoryReader",
    "ProjectRevisionHistorySnapshot",
    "ProjectSnapshot",
    "ReviseProjectCommand",
]
