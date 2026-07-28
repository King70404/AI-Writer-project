"""FastAPI dependencies for immutable Story Bible revision-history reads."""

from fastapi import Request

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.story_bible.application.history_queries import (
    DEFAULT_STORY_BIBLE_REVISION_HISTORY_LIMIT,
    GetStoryBibleRevisionQuery,
    ListStoryBibleRevisionsQuery,
    validate_story_bible_revision_history_limit,
)
from aiwebnovel.story_bible.application.history_service import (
    StoryBibleRevisionHistoryQueryService,
)
from aiwebnovel.story_bible.web.dependencies import get_story_bible_id
from aiwebnovel.story_bible.web.errors import (
    invalid_story_bible_revision_cursor,
    invalid_story_bible_revision_history_request,
    invalid_story_bible_revision_number,
    story_bible_history_service_unavailable,
)
from aiwebnovel.story_bible.web.history_cursor import (
    InvalidStoryBibleRevisionCursor,
    decode_story_bible_revision_cursor,
)


def get_story_bible_revision_history_query(
    request: Request,
    story_bible_id: str,
) -> ListStoryBibleRevisionsQuery:
    """Validate Story Bible, limit, then bind the optional opaque cursor."""
    canonical_story_bible_id = get_story_bible_id(story_bible_id)
    if any(key not in {"limit", "cursor"} for key in request.query_params):
        raise invalid_story_bible_revision_history_request()
    limit_values = request.query_params.getlist("limit")
    if len(limit_values) > 1:
        raise invalid_story_bible_revision_history_request()
    if limit_values:
        raw_limit = limit_values[0]
        if (
            not raw_limit
            or not raw_limit.isascii()
            or not raw_limit.isdecimal()
            or raw_limit.startswith("0")
        ):
            raise invalid_story_bible_revision_history_request()
        try:
            limit = validate_story_bible_revision_history_limit(int(raw_limit, 10))
        except (ValueError, OverflowError):
            raise invalid_story_bible_revision_history_request() from None
    else:
        limit = DEFAULT_STORY_BIBLE_REVISION_HISTORY_LIMIT

    cursor_values = request.query_params.getlist("cursor")
    if len(cursor_values) > 1:
        raise invalid_story_bible_revision_cursor()
    if cursor_values:
        try:
            after = decode_story_bible_revision_cursor(
                cursor_values[0],
                story_bible_id=canonical_story_bible_id,
            )
        except InvalidStoryBibleRevisionCursor as exc:
            raise invalid_story_bible_revision_cursor() from exc
    else:
        after = None
    return ListStoryBibleRevisionsQuery(
        story_bible_id=canonical_story_bible_id,
        limit=limit,
        after=after,
    )


def get_story_bible_revision_query(
    story_bible_id: str,
    revision_number: str,
) -> GetStoryBibleRevisionQuery:
    """Validate the identifier then parse one canonical positive decimal revision."""
    canonical_story_bible_id = get_story_bible_id(story_bible_id)
    if (
        not revision_number
        or not revision_number.isascii()
        or not revision_number.isdecimal()
        or revision_number.startswith("0")
    ):
        raise invalid_story_bible_revision_number()
    try:
        parsed_revision = RevisionNumber(int(revision_number, 10))
    except (DomainError, TypeError, ValueError, OverflowError):
        raise invalid_story_bible_revision_number() from None
    return GetStoryBibleRevisionQuery(
        story_bible_id=canonical_story_bible_id,
        revision_number=int(parsed_revision),
    )


def get_story_bible_revision_history_query_service(
    request: Request,
) -> StoryBibleRevisionHistoryQueryService:
    """Return this application's immutable history service or fail safely."""
    service = getattr(
        request.app.state,
        "story_bible_revision_history_query_service",
        None,
    )
    if not isinstance(service, StoryBibleRevisionHistoryQueryService):
        raise story_bible_history_service_unavailable()
    return service


__all__ = [
    "get_story_bible_revision_history_query",
    "get_story_bible_revision_history_query_service",
    "get_story_bible_revision_query",
]
