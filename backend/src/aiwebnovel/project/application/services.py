"""Project application command and query services over the public repository contract."""

from collections.abc import Callable

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import Clock, utc_now
from aiwebnovel.project.application.commands import (
    CreateProjectCommand,
    DeleteProjectCommand,
    ReviseProjectCommand,
)
from aiwebnovel.project.application.history import ProjectRevisionHistoryReader
from aiwebnovel.project.application.listing import ProjectListReader
from aiwebnovel.project.application.mappers import project_snapshot_from_aggregate
from aiwebnovel.project.application.models import (
    ProjectListPage,
    ProjectRevisionHistoryPage,
    ProjectRevisionHistorySnapshot,
    ProjectSnapshot,
)
from aiwebnovel.project.application.queries import (
    GetProjectQuery,
    GetProjectRevisionQuery,
    ListProjectRevisionsQuery,
    ListProjectsQuery,
    validate_project_list_limit,
    validate_project_revision_history_limit,
)
from aiwebnovel.project.deletion import deleted_project_title, is_reserved_project_title
from aiwebnovel.project.errors import InvalidProjectTitle, ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.repository import ProjectRepository
from aiwebnovel.project.transitions import create_initial_project
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

ProjectIdFactory = Callable[[], ProjectId]
ProjectRevisionIdFactory = Callable[[], ProjectRevisionId]


def _author_project_title(value: str) -> ProjectTitle:
    if is_reserved_project_title(value):
        raise InvalidProjectTitle
    return ProjectTitle(value)


class ProjectCommandService:
    """Execute one atomic repository write for each Project command."""

    def __init__(
        self,
        repository: ProjectRepository,
        *,
        clock: Clock = utc_now,
        project_id_factory: ProjectIdFactory = ProjectId.new,
        revision_id_factory: ProjectRevisionIdFactory = ProjectRevisionId.new,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._project_id_factory = project_id_factory
        self._revision_id_factory = revision_id_factory

    def create_project(self, command: CreateProjectCommand) -> ProjectSnapshot:
        """Validate raw input, construct one aggregate, and persist it atomically."""
        if type(command) is not CreateProjectCommand:
            raise TypeError("command must be a CreateProjectCommand")
        _author_project_title(command.title)
        aggregate = create_initial_project(
            command.title,
            command.description,
            clock=self._clock,
            project_id_factory=self._project_id_factory,
            revision_id_factory=self._revision_id_factory,
        )
        created = self._repository.create(aggregate)
        return project_snapshot_from_aggregate(created)

    def revise_project(self, command: ReviseProjectCommand) -> ProjectSnapshot:
        """Validate all raw input before requesting one atomic revision append."""
        if type(command) is not ReviseProjectCommand:
            raise TypeError("command must be a ReviseProjectCommand")
        project_id = ProjectId.parse(command.project_id)
        expected_version = ConcurrencyVersion(command.expected_version)
        title = _author_project_title(command.title)
        description = ProjectDescription(command.description)
        revised = self._repository.append_revision(
            project_id,
            expected_version,
            title,
            description,
            clock=self._clock,
            revision_id_factory=self._revision_id_factory,
        )
        return project_snapshot_from_aggregate(revised)

    def delete_project(self, command: DeleteProjectCommand) -> None:
        """Append an internal tombstone revision without deleting immutable history."""
        if type(command) is not DeleteProjectCommand:
            raise TypeError("command must be a DeleteProjectCommand")
        project_id = ProjectId.parse(command.project_id)
        expected_version = ConcurrencyVersion(command.expected_version)
        self._repository.append_revision(
            project_id,
            expected_version,
            ProjectTitle(deleted_project_title(project_id)),
            ProjectDescription(""),
            clock=self._clock,
            revision_id_factory=self._revision_id_factory,
        )


class ProjectQueryService:
    """Read detached current Project snapshots without application-side writes."""

    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    def overview_page(self, offset: int, limit: int) -> tuple[int, list[tuple[str, str]]]:
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid overview page")
        return self._repository.overview_page(offset, limit)

    def get_project(self, query: GetProjectQuery) -> ProjectSnapshot | None:
        """Return one current snapshot, or None when the Project does not exist."""
        if type(query) is not GetProjectQuery:
            raise TypeError("query must be a GetProjectQuery")
        project_id = ProjectId.parse(query.project_id)
        aggregate = self._repository.get(project_id)
        if aggregate is None:
            return None
        return project_snapshot_from_aggregate(aggregate)


class ProjectListQueryService:
    """Read one detached Project page through the dedicated list port."""

    def __init__(self, reader: ProjectListReader) -> None:
        self._reader = reader

    def list_projects(self, query: ListProjectsQuery) -> ProjectListPage:
        """Validate one query and delegate to the list reader exactly once."""
        if type(query) is not ListProjectsQuery:
            raise TypeError("query must be a ListProjectsQuery")
        limit = validate_project_list_limit(query.limit)
        return self._reader.list_page(limit=limit, after=query.after)


class ProjectRevisionHistoryQueryService:
    """Read immutable Project revisions while hiding deleted Projects from ordinary use."""

    def __init__(
        self,
        reader: ProjectRevisionHistoryReader,
        repository: ProjectRepository | None = None,
    ) -> None:
        self._reader = reader
        self._repository = repository

    def _require_active_project(self, project_id: ProjectId) -> None:
        if self._repository is not None and self._repository.get(project_id) is None:
            raise ProjectNotFound(project_id)

    def list_revisions(
        self,
        query: ListProjectRevisionsQuery,
    ) -> ProjectRevisionHistoryPage:
        if type(query) is not ListProjectRevisionsQuery:
            raise TypeError("query must be a ListProjectRevisionsQuery")
        project_id = ProjectId.parse(query.project_id)
        self._require_active_project(project_id)
        limit = validate_project_revision_history_limit(query.limit)
        after: RevisionNumber | None = None
        if query.after is not None:
            after_project_id = ProjectId.parse(query.after.project_id)
            if after_project_id != project_id:
                raise ValueError("after position must belong to the requested Project")
            after = RevisionNumber(query.after.revision_number)
        return self._reader.list_page(
            project_id=project_id,
            limit=limit,
            after=after,
        )

    def get_revision(
        self,
        query: GetProjectRevisionQuery,
    ) -> ProjectRevisionHistorySnapshot | None:
        if type(query) is not GetProjectRevisionQuery:
            raise TypeError("query must be a GetProjectRevisionQuery")
        project_id = ProjectId.parse(query.project_id)
        self._require_active_project(project_id)
        revision_number = RevisionNumber(query.revision_number)
        return self._reader.get_revision(
            project_id=project_id,
            revision_number=revision_number,
        )


__all__ = [
    "ProjectCommandService",
    "ProjectListQueryService",
    "ProjectQueryService",
    "ProjectRevisionHistoryQueryService",
]
