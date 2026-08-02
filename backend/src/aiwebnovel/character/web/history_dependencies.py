"""FastAPI dependencies for immutable Character revision-history reads."""

from fastapi import Request

from aiwebnovel.character.application.history_queries import (
    DEFAULT_CHARACTER_REVISION_HISTORY_LIMIT,
    GetCharacterRevisionQuery,
    ListCharacterRevisionsQuery,
    validate_character_revision_history_limit,
)
from aiwebnovel.character.application.history_service import CharacterRevisionHistoryQueryService
from aiwebnovel.character.web.dependencies import get_character_id
from aiwebnovel.character.web.errors import (
    character_history_service_unavailable,
    invalid_character_revision_cursor,
    invalid_character_revision_history_request,
    invalid_character_revision_number,
)
from aiwebnovel.character.web.history_cursor import (
    InvalidCharacterRevisionCursor,
    decode_character_revision_cursor,
)
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber


def get_character_revision_history_query(
    request: Request, character_id: str
) -> ListCharacterRevisionsQuery:
    canonical_character_id = get_character_id(character_id)
    if any(key not in {"limit", "cursor"} for key in request.query_params):
        raise invalid_character_revision_history_request()
    limit_values = request.query_params.getlist("limit")
    if len(limit_values) > 1:
        raise invalid_character_revision_history_request()
    if limit_values:
        raw_limit = limit_values[0]
        if (
            not raw_limit
            or not raw_limit.isascii()
            or not raw_limit.isdecimal()
            or raw_limit.startswith("0")
        ):
            raise invalid_character_revision_history_request()
        try:
            limit = validate_character_revision_history_limit(int(raw_limit, 10))
        except (ValueError, OverflowError):
            raise invalid_character_revision_history_request() from None
    else:
        limit = DEFAULT_CHARACTER_REVISION_HISTORY_LIMIT
    cursor_values = request.query_params.getlist("cursor")
    if len(cursor_values) > 1:
        raise invalid_character_revision_cursor()
    if cursor_values:
        try:
            after = decode_character_revision_cursor(
                cursor_values[0], character_id=canonical_character_id
            )
        except InvalidCharacterRevisionCursor as exc:
            raise invalid_character_revision_cursor() from exc
    else:
        after = None
    return ListCharacterRevisionsQuery(
        character_id=canonical_character_id, limit=limit, after=after
    )


def get_character_revision_query(
    character_id: str, revision_number: str
) -> GetCharacterRevisionQuery:
    canonical_character_id = get_character_id(character_id)
    if (
        not revision_number
        or not revision_number.isascii()
        or not revision_number.isdecimal()
        or revision_number.startswith("0")
    ):
        raise invalid_character_revision_number()
    try:
        parsed_revision = RevisionNumber(int(revision_number, 10))
    except (DomainError, TypeError, ValueError, OverflowError):
        raise invalid_character_revision_number() from None
    return GetCharacterRevisionQuery(
        character_id=canonical_character_id,
        revision_number=int(parsed_revision),
    )


def get_character_revision_history_query_service(
    request: Request,
) -> CharacterRevisionHistoryQueryService:
    service = getattr(request.app.state, "character_revision_history_query_service", None)
    if not isinstance(service, CharacterRevisionHistoryQueryService):
        raise character_history_service_unavailable()
    return service


__all__ = [
    "get_character_revision_history_query",
    "get_character_revision_history_query_service",
    "get_character_revision_query",
]
