"""Stable private Story Bible HTTP error mapping tests."""

import pytest
from tests.backend.story_bible_http_support import PROJECT_ID, STORY_BIBLE_ID

from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidDomainIdentifier
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.application.errors import StoryBibleForProjectNotFound
from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleContent,
    InvalidStoryBibleTitle,
    StoryBibleAlreadyExists,
    StoryBibleDataCorruption,
    StoryBibleForProjectAlreadyExists,
    StoryBibleNotFound,
    StoryBibleProjectNotFound,
    StoryBibleRepositoryError,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId
from aiwebnovel.story_bible.web.errors import raise_story_bible_http_error

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (InvalidStoryBibleTitle(), 422, "INVALID_STORY_BIBLE_TITLE"),
        (InvalidStoryBibleContent(), 422, "INVALID_STORY_BIBLE_CONTENT"),
        (
            StoryBibleForProjectNotFound(ProjectId.parse(PROJECT_ID)),
            404,
            "STORY_BIBLE_FOR_PROJECT_NOT_FOUND",
        ),
        (
            StoryBibleProjectNotFound(ProjectId.parse(PROJECT_ID)),
            404,
            "PROJECT_NOT_FOUND",
        ),
        (
            StoryBibleNotFound(StoryBibleId.parse(STORY_BIBLE_ID)),
            404,
            "STORY_BIBLE_NOT_FOUND",
        ),
        (
            StoryBibleForProjectAlreadyExists(ProjectId.parse(PROJECT_ID)),
            409,
            "STORY_BIBLE_ALREADY_EXISTS_FOR_PROJECT",
        ),
        (
            StoryBibleAlreadyExists(StoryBibleId.parse(STORY_BIBLE_ID)),
            409,
            "STORY_BIBLE_ID_CONFLICT",
        ),
        (
            ConcurrencyConflict(expected_version=1, actual_version=2),
            412,
            "STORY_BIBLE_VERSION_CONFLICT",
        ),
        (StoryBibleDataCorruption(), 500, "STORY_BIBLE_DATA_CORRUPTION"),
        (
            StoryBibleRepositoryError(),
            503,
            "STORY_BIBLE_PERSISTENCE_UNAVAILABLE",
        ),
        (InvalidDomainIdentifier(), 422, "INVALID_STORY_BIBLE_ID"),
    ],
)
def test_known_failures_map_to_stable_safe_http_errors(
    failure: Exception,
    status: int,
    code: str,
) -> None:
    with pytest.raises(AppError) as raised:
        raise_story_bible_http_error(failure)
    assert raised.value.status_code == status
    assert raised.value.code == code
    assert "STORY_BIBLE_HTTP_SECRET_CANARY" not in str(raised.value)


def test_concurrency_error_preserves_only_safe_versions() -> None:
    with pytest.raises(AppError) as raised:
        raise_story_bible_http_error(ConcurrencyConflict(expected_version=7, actual_version=8))
    assert raised.value.details == {"expected_version": 7, "actual_version": 8}


def test_unknown_failure_is_not_wrapped() -> None:
    failure = RuntimeError("STORY_BIBLE_HTTP_SECRET_CANARY")
    with pytest.raises(RuntimeError) as raised:
        raise_story_bible_http_error(failure)
    assert raised.value is failure
