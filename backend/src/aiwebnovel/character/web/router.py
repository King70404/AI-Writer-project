"""The four intentionally bounded Character HTTP endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from aiwebnovel.api.etags import format_strong_etag
from aiwebnovel.character.application.queries import (
    GetCharacterQuery,
    ListCharactersForProjectQuery,
)
from aiwebnovel.character.application.services import (
    CharacterCommandService,
    CharacterQueryService,
)
from aiwebnovel.character.web.dependencies import (
    get_character_command_service,
    get_character_id,
    get_character_list_query,
    get_character_project_id,
    get_character_query_service,
    get_required_character_version,
    require_character_json,
)
from aiwebnovel.character.web.dto import (
    CharacterListPageResponse,
    CharacterResponse,
    CreateCharacterRequest,
    ReviseCharacterRequest,
)
from aiwebnovel.character.web.errors import raise_character_http_error
from aiwebnovel.character.web.mappers import (
    character_list_page_response_from_page,
    character_response_from_snapshot,
    create_character_command_from_request,
    revise_character_command_from_request,
)
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError

_LIST_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "A stable Project-bound Character summary page.",
        "headers": {"Cache-Control": {"schema": {"type": "string"}}},
    },
    400: {"description": "The Project-bound Character cursor is invalid."},
    404: {"description": "Project not found."},
    422: {"description": "The Project identifier or list parameters are invalid."},
    500: {"description": "Stored Character list data is inconsistent."},
    503: {"description": "Character persistence or query service is unavailable."},
}
_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The complete current Character.",
        "headers": {
            "ETag": {"schema": {"type": "string"}},
            "Cache-Control": {"schema": {"type": "string"}},
        },
    },
    404: {"description": "Character not found."},
    422: {"description": "The Character identifier is invalid."},
    500: {"description": "Stored Character data is inconsistent."},
    503: {"description": "Character persistence or query service is unavailable."},
}
_CREATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "The Character was created.",
        "headers": {
            "ETag": {"schema": {"type": "string"}},
            "Location": {"schema": {"type": "string"}},
            "Cache-Control": {"schema": {"type": "string"}},
        },
    },
    403: {"description": "A trusted local session and CSRF context are required."},
    404: {"description": "The owning Project was not found."},
    409: {"description": "The generated Character identifier conflicts."},
    413: {"description": "The request body exceeds one MiB."},
    415: {"description": "A JSON media type is required."},
    422: {"description": "The request or a Character value is invalid."},
    500: {"description": "Stored Character data is inconsistent."},
    503: {"description": "Character persistence or command service is unavailable."},
}
_REVISE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The Character was completely revised.",
        "headers": {
            "ETag": {"schema": {"type": "string"}},
            "Cache-Control": {"schema": {"type": "string"}},
        },
    },
    400: {"description": "The If-Match header is malformed."},
    403: {"description": "A trusted local session and CSRF context are required."},
    404: {"description": "Character not found."},
    412: {"description": "The supplied Character version is stale."},
    413: {"description": "The request body exceeds one MiB."},
    415: {"description": "A JSON media type is required."},
    422: {"description": "The request or a Character value is invalid."},
    428: {"description": "If-Match is required."},
    500: {"description": "Stored Character data is inconsistent."},
    503: {"description": "Character persistence or command service is unavailable."},
}


def _set_character_headers(
    response: Response,
    character: CharacterResponse,
) -> None:
    response.headers["ETag"] = format_strong_etag(character.concurrency_version)
    response.headers["Cache-Control"] = "no-store"


def create_character_router(*, api_prefix: str) -> APIRouter:
    """Create the versioned Character router without touching persistence."""
    router = APIRouter(prefix=api_prefix, tags=["Character"])

    @router.get(
        "/projects/{project_id}/characters",
        response_model=CharacterListPageResponse,
        responses=_LIST_RESPONSES,
        summary="List a Project's current Characters",
        description=(
            "Returns current Character summaries ordered by created_at DESC and "
            "Character ID DESC using Project-bound keyset pagination. One Project may own "
            "many Characters and duplicate names are allowed. The opaque cursor is a strict "
            "position, not a security credential or cross-request database snapshot. "
            "Profile and total count are intentionally omitted; search and filtering are "
            "unsupported. Session, CSRF, and Origin are not required for this read."
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
                        "maximum": 100,
                        "default": 20,
                    },
                },
                {
                    "name": "cursor",
                    "in": "query",
                    "required": False,
                    "description": "Opaque keyset cursor bound to the Project in this path.",
                    "schema": {"type": "string", "nullable": True},
                },
            ]
        },
    )
    def list_characters(
        response: Response,
        query: Annotated[
            ListCharactersForProjectQuery,
            Depends(get_character_list_query),
        ],
        service: Annotated[
            CharacterQueryService,
            Depends(get_character_query_service),
        ],
    ) -> CharacterListPageResponse:
        try:
            page = service.list_characters_for_project(query)
        except DomainError as exc:
            raise_character_http_error(exc)
        result = character_list_page_response_from_page(page)
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.post(
        "/projects/{project_id}/characters",
        response_model=CharacterResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_CREATE_RESPONSES,
        summary="Create a Character for a Project",
        description=(
            "Creates one Character and its initial immutable complete revision. A Project "
            "may own many Characters and duplicate names are valid. A trusted local Session, "
            "same-origin request, and CSRF token are required. The strong ETag represents "
            "ConcurrencyVersion. Character history, relationships, delete, archive, restore, "
            "and AI generation are not exposed."
        ),
    )
    def create_character(
        response: Response,
        project_id: Annotated[str, Depends(get_character_project_id)],
        _json_content_type: Annotated[None, Depends(require_character_json)],
        payload: CreateCharacterRequest,
        service: Annotated[
            CharacterCommandService,
            Depends(get_character_command_service),
        ],
    ) -> CharacterResponse:
        command = create_character_command_from_request(project_id, payload)
        try:
            snapshot = service.create_character(command)
        except DomainError as exc:
            raise_character_http_error(exc)
        result = character_response_from_snapshot(snapshot)
        _set_character_headers(response, result)
        response.headers["Location"] = f"{api_prefix}/characters/{result.character_id}"
        return result

    @router.get(
        "/characters/{character_id}",
        response_model=CharacterResponse,
        responses=_READ_RESPONSES,
        summary="Get a current Character",
        description=(
            "Returns the complete current Character snapshot, including profile, by stable "
            "identifier. Session, CSRF, and Origin are not required. The strong ETag "
            "represents ConcurrencyVersion. Revision history and relationships are not exposed."
        ),
    )
    def get_character(
        response: Response,
        character_id: Annotated[str, Depends(get_character_id)],
        service: Annotated[
            CharacterQueryService,
            Depends(get_character_query_service),
        ],
    ) -> CharacterResponse:
        try:
            snapshot = service.get_character(GetCharacterQuery(character_id=character_id))
        except DomainError as exc:
            raise_character_http_error(exc)
        result = character_response_from_snapshot(snapshot)
        _set_character_headers(response, result)
        return result

    @router.put(
        "/characters/{character_id}",
        response_model=CharacterResponse,
        responses=_REVISE_RESPONSES,
        summary="Completely revise a Character",
        description=(
            "Completely replaces name, role, and profile; PATCH is intentionally unsupported. "
            "A trusted local Session, same-origin request, and CSRF token are required. "
            "If-Match must contain the current strong version ETag. The service does not "
            "pre-read, retry, replay, merge, or expose Revision history."
        ),
        openapi_extra={
            "parameters": [
                {
                    "name": "If-Match",
                    "in": "header",
                    "required": True,
                    "description": 'Required strong Character ETag, for example "1".',
                    "schema": {"type": "string"},
                }
            ]
        },
    )
    def revise_character(
        response: Response,
        character_id: Annotated[str, Depends(get_character_id)],
        _json_content_type: Annotated[None, Depends(require_character_json)],
        payload: ReviseCharacterRequest,
        expected_version: Annotated[
            ConcurrencyVersion,
            Depends(get_required_character_version),
        ],
        service: Annotated[
            CharacterCommandService,
            Depends(get_character_command_service),
        ],
    ) -> CharacterResponse:
        command = revise_character_command_from_request(
            character_id,
            int(expected_version),
            payload,
        )
        try:
            snapshot = service.revise_character(command)
        except DomainError as exc:
            raise_character_http_error(exc)
        result = character_response_from_snapshot(snapshot)
        _set_character_headers(response, result)
        return result

    return router


__all__ = ["create_character_router"]
