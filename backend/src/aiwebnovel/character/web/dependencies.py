"""FastAPI dependencies for composed Character application services."""

from fastapi import Request

from aiwebnovel.api.etags import InvalidIfMatch, parse_strong_if_match
from aiwebnovel.character.application.queries import (
    DEFAULT_CHARACTER_LIST_LIMIT,
    ListCharactersForProjectQuery,
    validate_character_list_limit,
)
from aiwebnovel.character.application.services import (
    CharacterCommandService,
    CharacterQueryService,
)
from aiwebnovel.character.identifiers import CharacterId
from aiwebnovel.character.web.cursor import (
    InvalidCharacterCursor,
    decode_character_cursor,
)
from aiwebnovel.character.web.errors import (
    character_command_service_unavailable,
    character_query_service_unavailable,
    invalid_character_cursor,
    invalid_character_id,
    invalid_character_list_request,
    invalid_if_match,
    invalid_project_id,
    precondition_required,
    unsupported_media_type,
)
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.security.request_limits import is_json_media_type


def get_character_project_id(project_id: str) -> str:
    """Validate and canonicalize a nested Project path identifier."""
    try:
        return str(ProjectId.parse(project_id))
    except InvalidDomainIdentifier as exc:
        raise invalid_project_id() from exc


def get_character_id(character_id: str) -> str:
    """Validate and canonicalize a Character path identifier."""
    try:
        return str(CharacterId.parse(character_id))
    except InvalidDomainIdentifier as exc:
        raise invalid_character_id() from exc


def get_required_character_version(request: Request) -> ConcurrencyVersion:
    """Require exactly one canonical shared strong If-Match value."""
    values = request.headers.getlist("If-Match")
    if not values:
        raise precondition_required()
    if len(values) != 1:
        raise invalid_if_match()
    try:
        return parse_strong_if_match(values[0])
    except InvalidIfMatch as exc:
        raise invalid_if_match() from exc


def require_character_json(request: Request) -> None:
    """Require one JSON Content-Type with no charset other than UTF-8."""
    values = request.headers.getlist("Content-Type")
    if len(values) != 1:
        raise unsupported_media_type()
    try:
        encoded = values[0].encode("ascii")
    except UnicodeEncodeError:
        raise unsupported_media_type() from None
    if not is_json_media_type(encoded):
        raise unsupported_media_type()
    parameters = [part.strip().lower() for part in values[0].split(";")[1:]]
    if any(parameter != "charset=utf-8" for parameter in parameters):
        raise unsupported_media_type()


def get_character_list_query(
    request: Request,
    project_id: str,
) -> ListCharactersForProjectQuery:
    """Validate Project, limit, then bind the optional Character cursor."""
    canonical_project_id = get_character_project_id(project_id)
    if any(key not in {"limit", "cursor"} for key in request.query_params):
        raise invalid_character_list_request()
    limit_values = request.query_params.getlist("limit")
    if len(limit_values) > 1:
        raise invalid_character_list_request()
    if limit_values:
        raw_limit = limit_values[0]
        if not raw_limit or not raw_limit.isascii() or not raw_limit.isdecimal():
            raise invalid_character_list_request()
        try:
            limit = validate_character_list_limit(int(raw_limit, 10))
        except (ValueError, OverflowError):
            raise invalid_character_list_request() from None
    else:
        limit = DEFAULT_CHARACTER_LIST_LIMIT

    cursor_values = request.query_params.getlist("cursor")
    if len(cursor_values) > 1:
        raise invalid_character_cursor()
    if cursor_values:
        try:
            after = decode_character_cursor(
                cursor_values[0],
                project_id=canonical_project_id,
            )
        except InvalidCharacterCursor as exc:
            raise invalid_character_cursor() from exc
    else:
        after = None
    return ListCharactersForProjectQuery(
        project_id=canonical_project_id,
        limit=limit,
        after=after,
    )


def get_character_command_service(request: Request) -> CharacterCommandService:
    """Return this application's command service or fail safely."""
    service = getattr(request.app.state, "character_command_service", None)
    if not isinstance(service, CharacterCommandService):
        raise character_command_service_unavailable()
    return service


def get_character_query_service(request: Request) -> CharacterQueryService:
    """Return this application's query service or fail safely."""
    service = getattr(request.app.state, "character_query_service", None)
    if not isinstance(service, CharacterQueryService):
        raise character_query_service_unavailable()
    return service


__all__ = [
    "get_character_command_service",
    "get_character_id",
    "get_character_list_query",
    "get_character_project_id",
    "get_character_query_service",
    "get_required_character_version",
    "require_character_json",
]
