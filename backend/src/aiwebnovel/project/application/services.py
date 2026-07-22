"""Project application command and query services over the public repository contract."""

from collections.abc import Callable

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock, utc_now
from aiwebnovel.project.application.commands import (
    CreateProjectCommand,
    ReviseProjectCommand,
)
from aiwebnovel.project.application.mappers import project_snapshot_from_aggregate
from aiwebnovel.project.application.models import ProjectSnapshot
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.repository import ProjectRepository
from aiwebnovel.project.transitions import create_initial_project
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

ProjectIdFactory = Callable[[], ProjectId]
ProjectRevisionIdFactory = Callable[[], ProjectRevisionId]


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
        title = ProjectTitle(command.title)
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


class ProjectQueryService:
    """Read detached current Project snapshots without application-side writes."""

    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    def get_project(self, query: GetProjectQuery) -> ProjectSnapshot | None:
        """Return one current snapshot, or None when the Project does not exist."""
        if type(query) is not GetProjectQuery:
            raise TypeError("query must be a GetProjectQuery")
        project_id = ProjectId.parse(query.project_id)
        aggregate = self._repository.get(project_id)
        if aggregate is None:
            return None
        return project_snapshot_from_aggregate(aggregate)


__all__ = ["ProjectCommandService", "ProjectQueryService"]
