"""Pure read port for immutable Project revision history."""

from typing import Protocol

from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.application.models import (
    ProjectRevisionHistoryPage,
    ProjectRevisionHistorySnapshot,
)
from aiwebnovel.project.identifiers import ProjectId


class ProjectRevisionHistoryReader(Protocol):
    """Read immutable revisions without exposing persistence objects."""

    def list_page(
        self,
        *,
        project_id: ProjectId,
        limit: int,
        after: RevisionNumber | None,
    ) -> ProjectRevisionHistoryPage: ...

    def get_revision(
        self,
        *,
        project_id: ProjectId,
        revision_number: RevisionNumber,
    ) -> ProjectRevisionHistorySnapshot | None: ...


__all__ = ["ProjectRevisionHistoryReader"]
