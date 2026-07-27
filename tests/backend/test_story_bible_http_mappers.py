"""Pure explicit Story Bible HTTP mapping tests."""

import pytest
from tests.backend.story_bible_http_support import (
    PROJECT_ID,
    STORY_BIBLE_ID,
    snapshot,
)

from aiwebnovel.story_bible.application.commands import (
    CreateStoryBibleCommand,
    ReviseStoryBibleCommand,
)
from aiwebnovel.story_bible.web.dto import (
    CreateStoryBibleRequest,
    ReviseStoryBibleRequest,
)
from aiwebnovel.story_bible.web.mappers import (
    create_story_bible_command_from_request,
    revise_story_bible_command_from_request,
    story_bible_response_from_snapshot,
)

pytestmark = pytest.mark.unit


def test_create_request_maps_each_field_without_mutation() -> None:
    request = CreateStoryBibleRequest(title=" Title ", content="A\r\nB")
    command = create_story_bible_command_from_request(PROJECT_ID, request)
    assert command == CreateStoryBibleCommand(PROJECT_ID, " Title ", "A\r\nB")
    assert request.title == " Title "
    assert request.content == "A\r\nB"


def test_revise_request_maps_each_field_without_mutation() -> None:
    request = ReviseStoryBibleRequest(title="Replacement", content="")
    command = revise_story_bible_command_from_request(STORY_BIBLE_ID, 7, request)
    assert command == ReviseStoryBibleCommand(
        STORY_BIBLE_ID,
        7,
        "Replacement",
        "",
    )


def test_snapshot_maps_every_response_field_and_is_detached() -> None:
    source = snapshot(version=2, title="Replacement", content="Complete")
    response = story_bible_response_from_snapshot(source)
    assert response.story_bible_id == source.story_bible_id
    assert response.project_id == source.project_id
    assert response.current_revision_id == source.current_revision_id
    assert response.revision_number == source.revision_number
    assert response.concurrency_version == source.concurrency_version
    assert response.title == source.title
    assert response.content == source.content
    assert response.created_at == source.created_at
    assert response.updated_at == source.updated_at
    assert response.revision_created_at == source.revision_created_at
    assert response.head_updated_at == source.head_updated_at


@pytest.mark.parametrize(
    "call",
    [
        lambda: create_story_bible_command_from_request(7, CreateStoryBibleRequest(title="T")),
        lambda: create_story_bible_command_from_request(PROJECT_ID, object()),
        lambda: revise_story_bible_command_from_request(
            7,
            1,
            ReviseStoryBibleRequest(title="T", content=""),
        ),
        lambda: revise_story_bible_command_from_request(
            STORY_BIBLE_ID,
            True,
            ReviseStoryBibleRequest(title="T", content=""),
        ),
        lambda: revise_story_bible_command_from_request(STORY_BIBLE_ID, 1, object()),
        lambda: story_bible_response_from_snapshot(object()),
    ],
)
def test_mappers_reject_wrong_exact_types_without_echo(call: object) -> None:
    with pytest.raises(TypeError) as raised:
        call()
    assert "STORY_BIBLE_HTTP_SECRET_CANARY" not in str(raised.value)
