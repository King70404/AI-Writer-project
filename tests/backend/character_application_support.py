"""Small Character application spies that never enter production."""

from __future__ import annotations

from collections.abc import Callable

from aiwebnovel.character.application.models import (
    CharacterListPage,
    CharacterListPosition,
)
from aiwebnovel.character.entities import CharacterAggregate
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.identifiers import ProjectId


class SpyCharacterRepository:
    """Configurable CharacterRepository spy with exact call recording."""

    def __init__(
        self,
        *,
        create_result: CharacterAggregate | None = None,
        get_result: CharacterAggregate | None = None,
        append_result: CharacterAggregate | None = None,
        create_error: Exception | None = None,
        get_error: Exception | None = None,
        append_error: Exception | None = None,
    ) -> None:
        self.create_result = create_result
        self.get_result = get_result
        self.append_result = append_result
        self.create_error = create_error
        self.get_error = get_error
        self.append_error = append_error
        self.create_calls: list[CharacterAggregate] = []
        self.get_calls: list[CharacterId] = []
        self.append_calls: list[
            tuple[
                CharacterId,
                ConcurrencyVersion,
                CharacterName,
                CharacterRole,
                CharacterProfile,
                Clock,
                Callable[[], CharacterRevisionId],
            ]
        ] = []

    def create(self, aggregate: CharacterAggregate) -> CharacterAggregate:
        self.create_calls.append(aggregate)
        if self.create_error is not None:
            raise self.create_error
        return aggregate if self.create_result is None else self.create_result

    def get(self, character_id: CharacterId) -> CharacterAggregate | None:
        self.get_calls.append(character_id)
        if self.get_error is not None:
            raise self.get_error
        return self.get_result

    def append_revision(
        self,
        character_id: CharacterId,
        *,
        expected_version: ConcurrencyVersion,
        name: CharacterName,
        role: CharacterRole,
        profile: CharacterProfile,
        clock: Clock,
        revision_id_factory: Callable[[], CharacterRevisionId],
    ) -> CharacterAggregate:
        self.append_calls.append(
            (
                character_id,
                expected_version,
                name,
                role,
                profile,
                clock,
                revision_id_factory,
            )
        )
        if self.append_error is not None:
            raise self.append_error
        if self.append_result is None:
            raise AssertionError("append_result must be configured")
        return self.append_result


class SpyCharacterListReader:
    """Configurable CharacterListReader spy."""

    def __init__(
        self,
        result: CharacterListPage,
        *,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[ProjectId, int, CharacterListPosition | None]] = []

    def list_for_project(
        self,
        project_id: ProjectId,
        *,
        limit: int,
        after: CharacterListPosition | None,
    ) -> CharacterListPage:
        self.calls.append((project_id, limit, after))
        if self.error is not None:
            raise self.error
        return self.result


__all__ = ["SpyCharacterListReader", "SpyCharacterRepository"]
