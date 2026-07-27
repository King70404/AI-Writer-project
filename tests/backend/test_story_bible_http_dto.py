"""Strict immutable Story Bible HTTP DTO tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from tests.backend.story_bible_http_support import BASE_TIME, snapshot

from aiwebnovel.story_bible.web.dto import (
    CreateStoryBibleRequest,
    ReviseStoryBibleRequest,
    StoryBibleResponse,
)
from aiwebnovel.story_bible.web.mappers import story_bible_response_from_snapshot

pytestmark = pytest.mark.unit


def test_create_request_has_exact_fields_default_and_is_frozen() -> None:
    request = CreateStoryBibleRequest(title="Title")
    assert request.title == "Title"
    assert request.content == ""
    assert set(type(request).model_fields) == {"title", "content"}
    with pytest.raises(ValidationError):
        request.title = "changed"


def test_revise_request_requires_complete_replacement_and_is_frozen() -> None:
    request = ReviseStoryBibleRequest(title="Title", content="")
    assert request.content == ""
    assert set(type(request).model_fields) == {"title", "content"}
    with pytest.raises(ValidationError):
        request.content = "changed"
    with pytest.raises(ValidationError):
        ReviseStoryBibleRequest.model_validate({"title": "Title"})


@pytest.mark.parametrize(
    "model,payload",
    [
        (CreateStoryBibleRequest, {"title": True}),
        (CreateStoryBibleRequest, {"title": "Title", "content": None}),
        (CreateStoryBibleRequest, {"title": "Title", "unknown": "value"}),
        (ReviseStoryBibleRequest, {"title": 7, "content": ""}),
        (ReviseStoryBibleRequest, {"title": "Title", "content": False}),
        (ReviseStoryBibleRequest, {"title": "Title", "content": "", "version": 1}),
    ],
)
def test_request_dtos_reject_coercion_null_and_extra_fields(
    model: type[CreateStoryBibleRequest] | type[ReviseStoryBibleRequest],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_response_has_exact_fields_and_is_frozen() -> None:
    response = story_bible_response_from_snapshot(snapshot())
    assert set(type(response).model_fields) == {
        "story_bible_id",
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "content",
        "created_at",
        "updated_at",
        "revision_created_at",
        "head_updated_at",
    }
    with pytest.raises(ValidationError):
        response.title = "changed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("revision_number", True),
        ("concurrency_version", False),
        ("revision_number", 0),
        ("concurrency_version", -1),
        ("story_bible_id", "sbl_invalid"),
        ("project_id", "prj_invalid"),
        ("current_revision_id", "sbr_invalid"),
        ("created_at", datetime(2026, 1, 1)),
        ("updated_at", datetime(2026, 1, 1, tzinfo=UTC).astimezone()),
    ],
)
def test_response_rejects_invalid_identifiers_versions_and_times(
    field: str,
    value: object,
) -> None:
    values = story_bible_response_from_snapshot(snapshot()).model_dump()
    values[field] = value
    with pytest.raises((ValidationError, TypeError, ValueError)):
        StoryBibleResponse.model_validate(values)


def test_response_rejects_version_and_timestamp_relationship_mismatches() -> None:
    values = story_bible_response_from_snapshot(snapshot()).model_dump()
    values["concurrency_version"] = 2
    with pytest.raises(ValidationError):
        StoryBibleResponse.model_validate(values)
    values = story_bible_response_from_snapshot(snapshot()).model_dump()
    values["head_updated_at"] = BASE_TIME.replace(microsecond=1)
    with pytest.raises(ValidationError):
        StoryBibleResponse.model_validate(values)


def test_response_error_hides_content_canary() -> None:
    canary = "STORY_BIBLE_HTTP_SECRET_CANARY"
    values = story_bible_response_from_snapshot(snapshot()).model_dump()
    values["title"] = canary + "\n"
    with pytest.raises(ValidationError) as raised:
        StoryBibleResponse.model_validate(values)
    assert canary not in str(raised.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", " Normalized title "),
        ("content", "A\r\nB"),
        ("content", "STORY_BIBLE_HTTP_SECRET_CANARY\u0000"),
    ],
)
def test_response_requires_canonical_text_without_echo(
    field: str,
    value: str,
) -> None:
    values = story_bible_response_from_snapshot(snapshot()).model_dump()
    values[field] = value
    with pytest.raises(ValidationError) as raised:
        StoryBibleResponse.model_validate(values)
    assert "STORY_BIBLE_HTTP_SECRET_CANARY" not in str(raised.value)
