"""Explicit Character HTTP mapping tests."""

import pytest
from tests.backend.character_http_support import PROJECT_ID, list_page, snapshot

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)
from aiwebnovel.character.web.dto import (
    CreateCharacterRequest,
    ReviseCharacterRequest,
)
from aiwebnovel.character.web.mappers import (
    character_list_page_response_from_page,
    character_response_from_snapshot,
    create_character_command_from_request,
    revise_character_command_from_request,
)


def test_request_mappers_copy_only_transport_owned_fields() -> None:
    assert create_character_command_from_request(
        PROJECT_ID,
        CreateCharacterRequest(name=" A ", role="R", profile="P\r\nQ"),
    ) == CreateCharacterCommand(PROJECT_ID, " A ", "R", "P\r\nQ")
    assert revise_character_command_from_request(
        snapshot().character_id,
        1,
        ReviseCharacterRequest(name="B", role="", profile=""),
    ) == ReviseCharacterCommand(snapshot().character_id, 1, "B", "", "")


def test_snapshot_and_page_mappers_are_explicit_and_profile_safe() -> None:
    response = character_response_from_snapshot(snapshot())
    assert response.model_dump()["character_id"] == snapshot().character_id
    cursor_calls = []
    page = character_list_page_response_from_page(
        list_page(),
        cursor_encoder=lambda position: cursor_calls.append(position) or "opaque",
    )
    assert page.next_cursor == "opaque"
    assert len(cursor_calls) == 1
    assert "profile" not in page.items[0].model_dump()


@pytest.mark.parametrize(
    "call",
    [
        lambda: character_response_from_snapshot(object()),  # type: ignore[arg-type]
        lambda: character_list_page_response_from_page(object()),  # type: ignore[arg-type]
        lambda: create_character_command_from_request(
            1,  # type: ignore[arg-type]
            CreateCharacterRequest(name="A"),
        ),
        lambda: create_character_command_from_request(
            PROJECT_ID,
            object(),  # type: ignore[arg-type]
        ),
        lambda: revise_character_command_from_request(
            1,  # type: ignore[arg-type]
            1,
            ReviseCharacterRequest(name="A", role="", profile=""),
        ),
        lambda: revise_character_command_from_request(
            snapshot().character_id,
            True,  # type: ignore[arg-type]
            ReviseCharacterRequest(name="A", role="", profile=""),
        ),
        lambda: revise_character_command_from_request(
            snapshot().character_id,
            1,
            object(),  # type: ignore[arg-type]
        ),
        lambda: character_list_page_response_from_page(
            list_page(),
            cursor_encoder=None,  # type: ignore[arg-type]
        ),
    ],
)
def test_mappers_reject_wrong_exact_types(call) -> None:
    with pytest.raises(TypeError):
        call()
