"""Read-only HTTP endpoints for immutable Character revision history."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from aiwebnovel.character.application.history_queries import (
    DEFAULT_CHARACTER_REVISION_HISTORY_LIMIT,
    MAX_CHARACTER_REVISION_HISTORY_LIMIT,
    GetCharacterRevisionQuery,
    ListCharacterRevisionsQuery,
)
from aiwebnovel.character.application.history_service import CharacterRevisionHistoryQueryService
from aiwebnovel.character.web.errors import raise_character_http_error
from aiwebnovel.character.web.history_dependencies import (
    get_character_revision_history_query,
    get_character_revision_history_query_service,
    get_character_revision_query,
)
from aiwebnovel.character.web.history_dto import (
    CharacterRevisionHistoryPageResponse,
    CharacterRevisionResponse,
)
from aiwebnovel.character.web.history_mappers import (
    character_revision_history_response_from_page,
    character_revision_response_from_snapshot,
)
from aiwebnovel.domain.errors import DomainError

_LIST_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The Character-bound keyset cursor is invalid."},
    404: {"description": "Character not found."},
    422: {"description": "The identifier or history query is invalid."},
    500: {"description": "Stored Character revision data is inconsistent."},
    503: {"description": "Character history persistence is unavailable."},
}
_REVISION_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Character or immutable revision not found."},
    422: {"description": "The identifier or revision number is invalid."},
    500: {"description": "Stored Character revision data is inconsistent."},
    503: {"description": "Character history persistence is unavailable."},
}


def create_character_history_router(*, api_prefix: str) -> APIRouter:
    """Create exactly two read-only history endpoints without persistence access."""
    router = APIRouter(prefix=f"{api_prefix}/characters", tags=["Character"])

    @router.get(
        "/{character_id}/revisions",
        response_model=CharacterRevisionHistoryPageResponse,
        responses=_LIST_RESPONSES,
        summary="List immutable Character revisions",
        description=(
            "Returns immutable summaries in RevisionNumber DESC order using a "
            "Character-bound keyset cursor. character_heads is the sole current-revision "
            "authority. Items omit profile and no total count is computed. This read-only "
            "endpoint has no session, CSRF, Origin, ETag, or If-Match requirement; revisions "
            "cannot be edited, diffed, restored, rolled back, or deleted."
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
                        "maximum": MAX_CHARACTER_REVISION_HISTORY_LIMIT,
                        "default": DEFAULT_CHARACTER_REVISION_HISTORY_LIMIT,
                    },
                },
                {
                    "name": "cursor",
                    "in": "query",
                    "required": False,
                    "description": "Opaque keyset cursor bound to the Character in this path.",
                    "schema": {"type": "string", "nullable": True},
                },
            ]
        },
    )
    def list_character_revisions(
        response: Response,
        query: Annotated[
            ListCharacterRevisionsQuery,
            Depends(get_character_revision_history_query),
        ],
        service: Annotated[
            CharacterRevisionHistoryQueryService,
            Depends(get_character_revision_history_query_service),
        ],
    ) -> CharacterRevisionHistoryPageResponse:
        try:
            page = service.list_revisions(query)
        except DomainError as exc:
            raise_character_http_error(exc)
        result = character_revision_history_response_from_page(page)
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.get(
        "/{character_id}/revisions/{revision_number}",
        response_model=CharacterRevisionResponse,
        responses=_REVISION_RESPONSES,
        summary="Get one immutable Character revision",
        description=(
            "Returns the original read-only name, role, and profile for one canonical positive "
            "RevisionNumber. character_heads remains the current authority. The endpoint has "
            "no session, CSRF, Origin, ETag, If-Match, editing, diff, restore, rollback, or "
            "history-write semantics."
        ),
    )
    def get_character_revision(
        response: Response,
        query: Annotated[
            GetCharacterRevisionQuery,
            Depends(get_character_revision_query),
        ],
        service: Annotated[
            CharacterRevisionHistoryQueryService,
            Depends(get_character_revision_history_query_service),
        ],
    ) -> CharacterRevisionResponse:
        try:
            snapshot = service.get_revision(query)
        except DomainError as exc:
            raise_character_http_error(exc)
        result = character_revision_response_from_snapshot(snapshot)
        response.headers["Cache-Control"] = "no-store"
        return result

    return router


__all__ = ["create_character_history_router"]
