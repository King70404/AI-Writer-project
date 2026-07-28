"""Read-only HTTP endpoints for immutable Story Bible revision history."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.story_bible.application.history_queries import (
    DEFAULT_STORY_BIBLE_REVISION_HISTORY_LIMIT,
    MAX_STORY_BIBLE_REVISION_HISTORY_LIMIT,
    GetStoryBibleRevisionQuery,
    ListStoryBibleRevisionsQuery,
)
from aiwebnovel.story_bible.application.history_service import (
    StoryBibleRevisionHistoryQueryService,
)
from aiwebnovel.story_bible.web.errors import raise_story_bible_http_error
from aiwebnovel.story_bible.web.history_dependencies import (
    get_story_bible_revision_history_query,
    get_story_bible_revision_history_query_service,
    get_story_bible_revision_query,
)
from aiwebnovel.story_bible.web.history_dto import (
    StoryBibleRevisionHistoryPageResponse,
    StoryBibleRevisionResponse,
)
from aiwebnovel.story_bible.web.history_mappers import (
    story_bible_revision_history_response_from_page,
    story_bible_revision_response_from_snapshot,
)

_LIST_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The Story Bible-bound keyset cursor is invalid."},
    404: {"description": "Story Bible not found."},
    422: {"description": "The identifier or history query is invalid."},
    500: {"description": "Stored Story Bible revision data is inconsistent."},
    503: {"description": "Story Bible history persistence is unavailable."},
}
_REVISION_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Story Bible or immutable revision not found."},
    422: {"description": "The identifier or revision number is invalid."},
    500: {"description": "Stored Story Bible revision data is inconsistent."},
    503: {"description": "Story Bible history persistence is unavailable."},
}


def create_story_bible_history_router(*, api_prefix: str) -> APIRouter:
    """Create two read-only endpoints without touching persistence."""
    router = APIRouter(
        prefix=f"{api_prefix}/story-bibles",
        tags=["Story Bible"],
    )

    @router.get(
        "/{story_bible_id}/revisions",
        response_model=StoryBibleRevisionHistoryPageResponse,
        responses=_LIST_RESPONSES,
        summary="List immutable Story Bible revisions",
        description=(
            "Returns immutable summaries in RevisionNumber DESC order using a "
            "Story-Bible-bound keyset cursor. Items omit content and no total count is "
            "computed. This read-only endpoint has no session or CSRF requirement; "
            "historical revisions cannot be edited, diffed, restored, or rolled back."
        ),
        openapi_extra={
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "description": "Page size from 1 through 100; defaults to 20.",
                    "schema": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_STORY_BIBLE_REVISION_HISTORY_LIMIT,
                        "default": DEFAULT_STORY_BIBLE_REVISION_HISTORY_LIMIT,
                    },
                },
                {
                    "name": "cursor",
                    "in": "query",
                    "required": False,
                    "description": ("Opaque keyset cursor bound to the Story Bible in this path."),
                    "schema": {"type": "string", "nullable": True},
                },
            ]
        },
    )
    def list_story_bible_revisions(
        response: Response,
        query: Annotated[
            ListStoryBibleRevisionsQuery,
            Depends(get_story_bible_revision_history_query),
        ],
        service: Annotated[
            StoryBibleRevisionHistoryQueryService,
            Depends(get_story_bible_revision_history_query_service),
        ],
    ) -> StoryBibleRevisionHistoryPageResponse:
        try:
            page = service.list_revisions(query)
        except DomainError as exc:
            raise_story_bible_http_error(exc)
        result = story_bible_revision_history_response_from_page(page)
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.get(
        "/{story_bible_id}/revisions/{revision_number}",
        response_model=StoryBibleRevisionResponse,
        responses=_REVISION_RESPONSES,
        summary="Get one immutable Story Bible revision",
        description=(
            "Returns the original read-only title and content for one canonical positive "
            "RevisionNumber. The endpoint has no ETag, session, CSRF, editing, diff, "
            "restore, or rollback semantics."
        ),
    )
    def get_story_bible_revision(
        response: Response,
        query: Annotated[
            GetStoryBibleRevisionQuery,
            Depends(get_story_bible_revision_query),
        ],
        service: Annotated[
            StoryBibleRevisionHistoryQueryService,
            Depends(get_story_bible_revision_history_query_service),
        ],
    ) -> StoryBibleRevisionResponse:
        try:
            snapshot = service.get_revision(query)
        except DomainError as exc:
            raise_story_bible_http_error(exc)
        result = story_bible_revision_response_from_snapshot(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return result

    return router


__all__ = ["create_story_bible_history_router"]
