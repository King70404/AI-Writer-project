"""Pure Project list read port owned by the Project application boundary."""

from typing import Protocol

from aiwebnovel.project.application.models import ProjectListPage, ProjectListPosition


class ProjectListReader(Protocol):
    """Read exactly one Project keyset page without exposing persistence values."""

    def list_page(
        self,
        *,
        limit: int,
        after: ProjectListPosition | None,
    ) -> ProjectListPage: ...


__all__ = ["ProjectListReader"]
