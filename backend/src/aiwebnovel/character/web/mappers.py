"""Explicit mappings between Character HTTP DTOs and application models."""

from collections.abc import Callable

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)
from aiwebnovel.character.application.models import (
    CharacterListItem,
    CharacterListPage,
    CharacterListPosition,
    CharacterSnapshot,
)
from aiwebnovel.character.web.cursor import encode_character_cursor
from aiwebnovel.character.web.dto import (
    CharacterListItemResponse,
    CharacterListPageResponse,
    CharacterResponse,
    CreateCharacterRequest,
    ReviseCharacterRequest,
)

CharacterCursorEncoder = Callable[[CharacterListPosition], str]


def create_character_command_from_request(
    project_id: str,
    request: CreateCharacterRequest,
) -> CreateCharacterCommand:
    """Map one canonical path Project and strict create request."""
    if type(project_id) is not str:
        raise TypeError("project_id must be a string")
    if type(request) is not CreateCharacterRequest:
        raise TypeError("request must be a CreateCharacterRequest")
    return CreateCharacterCommand(
        project_id=project_id,
        name=request.name,
        role=request.role,
        profile=request.profile,
    )


def revise_character_command_from_request(
    character_id: str,
    expected_version: int,
    request: ReviseCharacterRequest,
) -> ReviseCharacterCommand:
    """Map one Character path, ETag version, and complete replacement."""
    if type(character_id) is not str:
        raise TypeError("character_id must be a string")
    if type(expected_version) is not int:
        raise TypeError("expected_version must be an integer")
    if type(request) is not ReviseCharacterRequest:
        raise TypeError("request must be a ReviseCharacterRequest")
    return ReviseCharacterCommand(
        character_id=character_id,
        expected_version=expected_version,
        name=request.name,
        role=request.role,
        profile=request.profile,
    )


def character_response_from_snapshot(snapshot: CharacterSnapshot) -> CharacterResponse:
    """Copy every current snapshot field into the complete response DTO."""
    if type(snapshot) is not CharacterSnapshot:
        raise TypeError("snapshot must be a CharacterSnapshot")
    return CharacterResponse(
        character_id=snapshot.character_id,
        project_id=snapshot.project_id,
        current_revision_id=snapshot.current_revision_id,
        revision_number=snapshot.revision_number,
        concurrency_version=snapshot.concurrency_version,
        name=snapshot.name,
        role=snapshot.role,
        profile=snapshot.profile,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        revision_created_at=snapshot.revision_created_at,
        head_updated_at=snapshot.head_updated_at,
    )


def _character_list_item_response(
    item: CharacterListItem,
) -> CharacterListItemResponse:
    if type(item) is not CharacterListItem:
        raise TypeError("item must be a CharacterListItem")
    return CharacterListItemResponse(
        character_id=item.character_id,
        current_revision_id=item.current_revision_id,
        revision_number=item.revision_number,
        concurrency_version=item.concurrency_version,
        name=item.name,
        role=item.role,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def character_list_page_response_from_page(
    page: CharacterListPage,
    *,
    cursor_encoder: CharacterCursorEncoder = encode_character_cursor,
) -> CharacterListPageResponse:
    """Map a detached page and explicitly encode only its next position."""
    if type(page) is not CharacterListPage:
        raise TypeError("page must be a CharacterListPage")
    if not callable(cursor_encoder):
        raise TypeError("cursor_encoder must be callable")
    next_cursor = cursor_encoder(page.next_position) if page.next_position is not None else None
    return CharacterListPageResponse(
        project_id=page.project_id,
        items=tuple(_character_list_item_response(item) for item in page.items),
        next_cursor=next_cursor,
        has_more=page.has_more,
    )


__all__ = [
    "character_list_page_response_from_page",
    "character_response_from_snapshot",
    "create_character_command_from_request",
    "revise_character_command_from_request",
]
