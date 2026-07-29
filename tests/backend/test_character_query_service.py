"""Character query-service strictness and exact port usage."""

import pytest
from tests.backend.character_application_support import (
    SpyCharacterListReader,
    SpyCharacterRepository,
)
from tests.backend.character_repository_support import (
    BASE_TIME,
    character_aggregate,
    character_id,
    project_id,
)

from aiwebnovel.character.application.models import (
    CharacterListPage,
    CharacterListPosition,
)
from aiwebnovel.character.application.queries import (
    GetCharacterQuery,
    ListCharactersForProjectQuery,
)
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.character.errors import (
    CharacterDataCorruption,
    CharacterNotFound,
    CharacterProjectNotFound,
    CharacterRepositoryError,
)
from aiwebnovel.domain.errors import InvalidDomainIdentifier


def empty_page(project_value: int = 1) -> CharacterListPage:
    return CharacterListPage(str(project_id(project_value)), (), None, False)


def service_with(
    repository: SpyCharacterRepository,
    reader: SpyCharacterListReader | None = None,
) -> CharacterQueryService:
    return CharacterQueryService(
        repository,
        reader or SpyCharacterListReader(empty_page()),
    )


def test_get_calls_only_repository_get_once_and_maps_snapshot() -> None:
    repository = SpyCharacterRepository(get_result=character_aggregate(1))
    reader = SpyCharacterListReader(empty_page())

    snapshot = service_with(repository, reader).get_character(
        GetCharacterQuery(str(character_id(1)))
    )

    assert snapshot.character_id == str(character_id(1))
    assert repository.get_calls == [character_id(1)]
    assert repository.create_calls == []
    assert repository.append_calls == []
    assert reader.calls == []


def test_get_none_becomes_precise_not_found() -> None:
    repository = SpyCharacterRepository()

    with pytest.raises(CharacterNotFound) as captured:
        service_with(repository).get_character(GetCharacterQuery(str(character_id(1))))

    assert captured.value.character_id == character_id(1)
    assert repository.get_calls == [character_id(1)]


@pytest.mark.parametrize(
    "query",
    [object(), GetCharacterQuery("invalid"), GetCharacterQuery(1)],  # type: ignore[list-item]
)
def test_get_invalid_query_never_calls_any_port(query: object) -> None:
    repository = SpyCharacterRepository()
    reader = SpyCharacterListReader(empty_page())

    with pytest.raises((TypeError, InvalidDomainIdentifier)):
        service_with(repository, reader).get_character(query)  # type: ignore[arg-type]

    assert repository.get_calls == []
    assert reader.calls == []


@pytest.mark.parametrize(
    "failure",
    [CharacterDataCorruption(), CharacterRepositoryError()],
)
def test_get_repository_failures_propagate_unchanged(failure: Exception) -> None:
    repository = SpyCharacterRepository(get_error=failure)

    with pytest.raises(type(failure)) as captured:
        service_with(repository).get_character(GetCharacterQuery(str(character_id(1))))

    assert captured.value is failure
    assert len(repository.get_calls) == 1


def test_list_calls_only_reader_once_and_returns_its_authoritative_page() -> None:
    repository = SpyCharacterRepository()
    page = empty_page()
    reader = SpyCharacterListReader(page)

    result = service_with(repository, reader).list_characters_for_project(
        ListCharactersForProjectQuery(str(project_id(1)), limit=20)
    )

    assert result is page
    assert reader.calls == [(project_id(1), 20, None)]
    assert repository.get_calls == []
    assert repository.create_calls == []
    assert repository.append_calls == []


def test_list_passes_project_bound_position_unchanged() -> None:
    position = CharacterListPosition(project_id(1), BASE_TIME, character_id(1))
    reader = SpyCharacterListReader(empty_page())

    service_with(SpyCharacterRepository(), reader).list_characters_for_project(
        ListCharactersForProjectQuery(
            str(project_id(1)),
            limit=7,
            after=position,
        )
    )

    assert reader.calls == [(project_id(1), 7, position)]


@pytest.mark.parametrize(
    "query",
    [
        object(),
        ListCharactersForProjectQuery("invalid"),
        ListCharactersForProjectQuery(1),  # type: ignore[arg-type]
        ListCharactersForProjectQuery(
            str(project_id(1)),
            after=CharacterListPosition(project_id(2), BASE_TIME, character_id(1)),
        ),
    ],
)
def test_list_invalid_query_never_calls_any_port(query: object) -> None:
    repository = SpyCharacterRepository()
    reader = SpyCharacterListReader(empty_page())

    with pytest.raises((TypeError, ValueError, InvalidDomainIdentifier)):
        service_with(repository, reader).list_characters_for_project(
            query  # type: ignore[arg-type]
        )

    assert reader.calls == []
    assert repository.get_calls == []


@pytest.mark.parametrize(
    "failure",
    [
        CharacterProjectNotFound(project_id(1)),
        CharacterDataCorruption(),
        CharacterRepositoryError(),
    ],
)
def test_list_reader_failures_propagate_unchanged(failure: Exception) -> None:
    reader = SpyCharacterListReader(empty_page(), error=failure)

    with pytest.raises(type(failure)) as captured:
        service_with(SpyCharacterRepository(), reader).list_characters_for_project(
            ListCharactersForProjectQuery(str(project_id(1)))
        )

    assert captured.value is failure
    assert len(reader.calls) == 1
