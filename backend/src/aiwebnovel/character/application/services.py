"""Character application services over pure Python ports."""

from collections.abc import Callable

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)
from aiwebnovel.character.application.list_reader import CharacterListReader
from aiwebnovel.character.application.mappers import (
    character_snapshot_from_aggregate,
)
from aiwebnovel.character.application.models import (
    CharacterListPage,
    CharacterSnapshot,
)
from aiwebnovel.character.application.queries import (
    GetCharacterQuery,
    ListCharactersForProjectQuery,
    validate_character_list_limit,
)
from aiwebnovel.character.errors import (
    CharacterNotFound,
    CharacterProjectNotFound,
)
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.repository import CharacterRepository
from aiwebnovel.character.transitions import create_initial_character
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.repository import ProjectRepository

CharacterIdFactory = Callable[[], CharacterId]
CharacterRevisionIdFactory = Callable[[], CharacterRevisionId]


def _character_id_from_factory(factory: CharacterIdFactory) -> CharacterId:
    identifier = factory()
    if type(identifier) is not CharacterId:
        raise TypeError("character_id_factory must return a CharacterId")
    return identifier


def _revision_id_from_factory(
    factory: CharacterRevisionIdFactory,
) -> CharacterRevisionId:
    identifier = factory()
    if type(identifier) is not CharacterRevisionId:
        raise TypeError("revision_id_factory must return a CharacterRevisionId")
    return identifier


class _ProjectVisibilityMixin:
    _project_repository: ProjectRepository | None

    def _require_active_project(self, project_id: ProjectId) -> None:
        if self._project_repository is not None and self._project_repository.get(project_id) is None:
            raise CharacterProjectNotFound(project_id)


class CharacterCommandService(_ProjectVisibilityMixin):
    """Execute one atomic Character repository write per command."""

    def __init__(
        self,
        repository: CharacterRepository,
        clock: Clock,
        character_id_factory: CharacterIdFactory,
        revision_id_factory: CharacterRevisionIdFactory,
        project_repository: ProjectRepository | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._character_id_factory = character_id_factory
        self._revision_id_factory = revision_id_factory
        self._project_repository = project_repository

    def create_character(
        self,
        command: CreateCharacterCommand,
    ) -> CharacterSnapshot:
        if type(command) is not CreateCharacterCommand:
            raise TypeError("command must be a CreateCharacterCommand")
        project_id = ProjectId.parse(command.project_id)
        self._require_active_project(project_id)
        name = CharacterName(command.name)
        role = CharacterRole(command.role)
        profile = CharacterProfile(command.profile)
        now = self._clock()
        character_id = _character_id_from_factory(self._character_id_factory)
        revision_id = _revision_id_from_factory(self._revision_id_factory)
        aggregate = create_initial_character(
            character_id=character_id,
            revision_id=revision_id,
            project_id=project_id,
            name=name,
            role=role,
            profile=profile,
            now=now,
        )
        created = self._repository.create(aggregate)
        return character_snapshot_from_aggregate(created)

    def revise_character(
        self,
        command: ReviseCharacterCommand,
    ) -> CharacterSnapshot:
        if type(command) is not ReviseCharacterCommand:
            raise TypeError("command must be a ReviseCharacterCommand")
        character_id = CharacterId.parse(command.character_id)
        if self._project_repository is not None:
            current = self._repository.get(character_id)
            if current is None:
                raise CharacterNotFound(character_id)
            self._require_active_project(current.character.project_id)
        expected_version = ConcurrencyVersion(command.expected_version)
        name = CharacterName(command.name)
        role = CharacterRole(command.role)
        profile = CharacterProfile(command.profile)
        revised = self._repository.append_revision(
            character_id,
            expected_version=expected_version,
            name=name,
            role=role,
            profile=profile,
            clock=self._clock,
            revision_id_factory=self._revision_id_factory,
        )
        return character_snapshot_from_aggregate(revised)


class CharacterQueryService(_ProjectVisibilityMixin):
    """Read current Character snapshots and stable list pages."""

    def __init__(
        self,
        repository: CharacterRepository,
        list_reader: CharacterListReader,
        project_repository: ProjectRepository | None = None,
    ) -> None:
        self._repository = repository
        self._list_reader = list_reader
        self._project_repository = project_repository

    def get_character(
        self,
        query: GetCharacterQuery,
    ) -> CharacterSnapshot:
        if type(query) is not GetCharacterQuery:
            raise TypeError("query must be a GetCharacterQuery")
        character_id = CharacterId.parse(query.character_id)
        aggregate = self._repository.get(character_id)
        if aggregate is None:
            raise CharacterNotFound(character_id)
        self._require_active_project(aggregate.character.project_id)
        return character_snapshot_from_aggregate(aggregate)

    def list_characters_for_project(
        self,
        query: ListCharactersForProjectQuery,
    ) -> CharacterListPage:
        if type(query) is not ListCharactersForProjectQuery:
            raise TypeError("query must be a ListCharactersForProjectQuery")
        project_id = ProjectId.parse(query.project_id)
        self._require_active_project(project_id)
        limit = validate_character_list_limit(query.limit)
        if query.after is not None and query.after.project_id != project_id:
            raise ValueError("after position must belong to the requested Project")
        return self._list_reader.list_for_project(
            project_id,
            limit=limit,
            after=query.after,
        )


__all__ = ["CharacterCommandService", "CharacterQueryService"]
