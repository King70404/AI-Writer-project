"""Explicit mappings from Story Bible history models to HTTP DTOs."""

from aiwebnovel.story_bible.application.history_models import (
    StoryBibleRevisionHistoryPage,
    StoryBibleRevisionSnapshot,
)
from aiwebnovel.story_bible.web.history_cursor import (
    encode_story_bible_revision_cursor,
)
from aiwebnovel.story_bible.web.history_dto import (
    StoryBibleRevisionHistoryItemResponse,
    StoryBibleRevisionHistoryPageResponse,
    StoryBibleRevisionResponse,
)


def story_bible_revision_history_response_from_page(
    page: StoryBibleRevisionHistoryPage,
) -> StoryBibleRevisionHistoryPageResponse:
    """Copy one application page and encode only its next position."""
    if type(page) is not StoryBibleRevisionHistoryPage:
        raise TypeError("page must be a StoryBibleRevisionHistoryPage")
    return StoryBibleRevisionHistoryPageResponse(
        story_bible_id=page.story_bible_id,
        project_id=page.project_id,
        current_revision_number=page.current_revision_number,
        items=tuple(
            StoryBibleRevisionHistoryItemResponse(
                revision_id=item.revision_id,
                revision_number=item.revision_number,
                title=item.title,
                created_at=item.created_at,
                is_current=item.is_current,
            )
            for item in page.items
        ),
        next_cursor=(
            encode_story_bible_revision_cursor(page.next_position)
            if page.next_position is not None
            else None
        ),
        has_more=page.has_more,
    )


def story_bible_revision_response_from_snapshot(
    snapshot: StoryBibleRevisionSnapshot,
) -> StoryBibleRevisionResponse:
    """Copy every immutable revision field into the response DTO."""
    if type(snapshot) is not StoryBibleRevisionSnapshot:
        raise TypeError("snapshot must be a StoryBibleRevisionSnapshot")
    return StoryBibleRevisionResponse(
        story_bible_id=snapshot.story_bible_id,
        project_id=snapshot.project_id,
        revision_id=snapshot.revision_id,
        revision_number=snapshot.revision_number,
        title=snapshot.title,
        content=snapshot.content,
        created_at=snapshot.created_at,
        is_current=snapshot.is_current,
        current_revision_number=snapshot.current_revision_number,
    )


__all__ = [
    "story_bible_revision_history_response_from_page",
    "story_bible_revision_response_from_snapshot",
]
