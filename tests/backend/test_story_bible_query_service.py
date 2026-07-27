"""Story Bible query-service strictness and exact absence semantics."""

import pytest
from tests.backend.story_bible_application_support import (
    SpyStoryBibleRepository,
)
from tests.backend.story_bible_support import (
    initial_aggregate,
    project_id,
    story_bible_id,
)

from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.story_bible.application.errors import (
    StoryBibleForProjectNotFound,
)
from aiwebnovel.story_bible.application.queries import (
    GetStoryBibleForProjectQuery,
    GetStoryBibleQuery,
)
from aiwebnovel.story_bible.application.services import StoryBibleQueryService
from aiwebnovel.story_bible.errors import (
    StoryBibleDataCorruption,
    StoryBibleNotFound,
    StoryBibleProjectNotFound,
    StoryBibleRepositoryError,
)

CANARY = "STORY_BIBLE_APPLICATION_SECRET_CANARY"


def test_get_by_id_calls_only_get_once_and_maps_snapshot() -> None:
    repository = SpyStoryBibleRepository(get_result=initial_aggregate())
    service = StoryBibleQueryService(repository)

    snapshot = service.get_story_bible(GetStoryBibleQuery(str(story_bible_id())))

    assert snapshot.story_bible_id == str(story_bible_id())
    assert repository.get_calls == [story_bible_id()]
    assert repository.get_for_project_calls == []
    assert repository.create_calls == []
    assert repository.append_calls == []


def test_get_by_id_none_becomes_precise_not_found() -> None:
    repository = SpyStoryBibleRepository()

    with pytest.raises(StoryBibleNotFound) as captured:
        StoryBibleQueryService(repository).get_story_bible(
            GetStoryBibleQuery(str(story_bible_id()))
        )

    assert captured.value.story_bible_id == story_bible_id()
    assert repository.get_calls == [story_bible_id()]


@pytest.mark.parametrize(
    "query",
    [object(), GetStoryBibleQuery("invalid"), GetStoryBibleQuery(1)],  # type: ignore[list-item]
)
def test_get_by_id_invalid_query_never_calls_repository(query: object) -> None:
    repository = SpyStoryBibleRepository()

    with pytest.raises((TypeError, InvalidDomainIdentifier)):
        StoryBibleQueryService(repository).get_story_bible(query)  # type: ignore[arg-type]

    assert repository.get_calls == []


@pytest.mark.parametrize(
    "failure",
    [StoryBibleDataCorruption(), StoryBibleRepositoryError()],
)
def test_get_by_id_propagates_repository_failures(failure: Exception) -> None:
    repository = SpyStoryBibleRepository(get_error=failure)

    with pytest.raises(type(failure)) as captured:
        StoryBibleQueryService(repository).get_story_bible(
            GetStoryBibleQuery(str(story_bible_id()))
        )

    assert captured.value is failure
    assert len(repository.get_calls) == 1


def test_get_for_project_calls_only_project_query_once_and_maps_snapshot() -> None:
    repository = SpyStoryBibleRepository(get_for_project_result=initial_aggregate())
    service = StoryBibleQueryService(repository)

    snapshot = service.get_story_bible_for_project(GetStoryBibleForProjectQuery(str(project_id())))

    assert snapshot.project_id == str(project_id())
    assert repository.get_for_project_calls == [project_id()]
    assert repository.get_calls == []
    assert repository.create_calls == []
    assert repository.append_calls == []


def test_existing_project_without_story_bible_has_application_absence_error() -> None:
    repository = SpyStoryBibleRepository()

    with pytest.raises(StoryBibleForProjectNotFound) as captured:
        StoryBibleQueryService(repository).get_story_bible_for_project(
            GetStoryBibleForProjectQuery(str(project_id()))
        )

    assert captured.value.project_id == project_id()
    assert str(captured.value) == "The Project does not have a Story Bible."
    assert len(repository.get_for_project_calls) == 1


def test_application_absence_error_rejects_wrong_internal_identifier() -> None:
    with pytest.raises(TypeError, match=r"^project_id must be a ProjectId$"):
        StoryBibleForProjectNotFound("invalid")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "query",
    [
        object(),
        GetStoryBibleForProjectQuery("invalid"),
        GetStoryBibleForProjectQuery(1),  # type: ignore[arg-type]
    ],
)
def test_get_for_project_invalid_query_never_calls_repository(query: object) -> None:
    repository = SpyStoryBibleRepository()

    with pytest.raises((TypeError, InvalidDomainIdentifier)):
        StoryBibleQueryService(repository).get_story_bible_for_project(
            query  # type: ignore[arg-type]
        )

    assert repository.get_for_project_calls == []


@pytest.mark.parametrize(
    "failure",
    [
        StoryBibleProjectNotFound(project_id()),
        StoryBibleDataCorruption(),
        StoryBibleRepositoryError(),
    ],
)
def test_get_for_project_propagates_distinct_repository_failures(
    failure: Exception,
) -> None:
    repository = SpyStoryBibleRepository(get_for_project_error=failure)

    with pytest.raises(type(failure)) as captured:
        StoryBibleQueryService(repository).get_story_bible_for_project(
            GetStoryBibleForProjectQuery(str(project_id()))
        )

    assert captured.value is failure
    assert len(repository.get_for_project_calls) == 1
    assert CANARY not in str(captured.value)
