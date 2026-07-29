"""Pure Character list read port owned by the application boundary."""

from typing import Protocol

from aiwebnovel.character.application.models import (
    CharacterListPage,
    CharacterListPosition,
)
from aiwebnovel.project.identifiers import ProjectId


class CharacterListReader(Protocol):
    """Read one Project-bound Character page without persistence values."""

    def list_for_project(
        self,
        project_id: ProjectId,
        *,
        limit: int,
        after: CharacterListPosition | None,
    ) -> CharacterListPage: ...


__all__ = ["CharacterListReader"]
