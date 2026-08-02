"""Explicit mappings from Character history models to HTTP DTOs."""

from aiwebnovel.character.application.history_models import (
    CharacterRevisionHistoryPage,
    CharacterRevisionSnapshot,
)
from aiwebnovel.character.web.history_cursor import encode_character_revision_cursor
from aiwebnovel.character.web.history_dto import (
    CharacterRevisionHistoryItemResponse,
    CharacterRevisionHistoryPageResponse,
    CharacterRevisionResponse,
)


def character_revision_history_response_from_page(
    page: CharacterRevisionHistoryPage,
) -> CharacterRevisionHistoryPageResponse:
    if type(page) is not CharacterRevisionHistoryPage:
        raise TypeError("page must be a CharacterRevisionHistoryPage")
    return CharacterRevisionHistoryPageResponse(
        character_id=page.character_id,
        project_id=page.project_id,
        current_revision_number=page.current_revision_number,
        items=tuple(
            CharacterRevisionHistoryItemResponse(
                revision_id=item.revision_id,
                revision_number=item.revision_number,
                name=item.name,
                role=item.role,
                created_at=item.created_at,
                is_current=item.is_current,
            )
            for item in page.items
        ),
        next_cursor=(
            encode_character_revision_cursor(page.next_position)
            if page.next_position is not None
            else None
        ),
        has_more=page.has_more,
    )


def character_revision_response_from_snapshot(
    snapshot: CharacterRevisionSnapshot,
) -> CharacterRevisionResponse:
    if type(snapshot) is not CharacterRevisionSnapshot:
        raise TypeError("snapshot must be a CharacterRevisionSnapshot")
    return CharacterRevisionResponse(
        character_id=snapshot.character_id,
        project_id=snapshot.project_id,
        revision_id=snapshot.revision_id,
        revision_number=snapshot.revision_number,
        name=snapshot.name,
        role=snapshot.role,
        profile=snapshot.profile,
        created_at=snapshot.created_at,
        is_current=snapshot.is_current,
        current_revision_number=snapshot.current_revision_number,
    )


__all__ = [
    "character_revision_history_response_from_page",
    "character_revision_response_from_snapshot",
]
