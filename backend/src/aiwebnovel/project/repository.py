"""Framework-independent persistence contract owned by the Project module."""

from collections.abc import Callable
from typing import Protocol

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.values import ProjectDescription, ProjectTitle


class ProjectRepository(Protocol):
    """Store and restore only the current Project aggregate transactionally."""

    def overview_page(self, offset: int, limit: int) -> tuple[int, list[tuple[str, str]]]:
        """Read a bounded page of active project identifiers and current titles."""
        ...

    def create(self, aggregate: ProjectAggregate) -> ProjectAggregate:
        """Atomically persist a new Project, its first revision, and its head."""
        ...

    def get(self, project_id: ProjectId) -> ProjectAggregate | None:
        """Return one consistent active aggregate, or None when absent/deleted."""
        ...

    def append_revision(
        self,
        project_id: ProjectId,
        expected_version: ConcurrencyVersion,
        title: ProjectTitle,
        description: ProjectDescription,
        *,
        clock: Clock | None = None,
        revision_id_factory: Callable[[], ProjectRevisionId] = ProjectRevisionId.new,
    ) -> ProjectAggregate:
        """Atomically append one immutable revision using Project and Head CAS."""
        ...


__all__ = ["ProjectRepository"]
