"""The four intentionally bounded Story Bible HTTP endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from aiwebnovel.api.etags import format_strong_etag
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.story_bible.application.queries import (
    GetStoryBibleForProjectQuery,
    GetStoryBibleQuery,
)
from aiwebnovel.story_bible.application.services import (
    StoryBibleCommandService,
    StoryBibleQueryService,
)
from aiwebnovel.story_bible.web.dependencies import (
    get_required_story_bible_version,
    get_story_bible_command_service,
    get_story_bible_id,
    get_story_bible_project_id,
    get_story_bible_query_service,
    require_story_bible_json,
)
from aiwebnovel.story_bible.web.dto import (
    CreateStoryBibleRequest,
    ReviseStoryBibleRequest,
    StoryBibleResponse,
)
from aiwebnovel.story_bible.web.errors import raise_story_bible_http_error
from aiwebnovel.story_bible.web.mappers import (
    create_story_bible_command_from_request,
    revise_story_bible_command_from_request,
    story_bible_response_from_snapshot,
)

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "Project or Story Bible not found."},
    422: {"description": "The path identifier is invalid."},
    500: {"description": "Stored Story Bible data is inconsistent."},
    503: {"description": "Story Bible persistence or service is unavailable."},
}
_CREATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"description": "A trusted local session and CSRF context are required."},
    404: {"description": "The owning Project was not found."},
    409: {"description": "The Project already has a Story Bible or the ID conflicts."},
    413: {"description": "The request body exceeds one MiB."},
    415: {"description": "A JSON media type is required."},
    422: {"description": "The request or a Story Bible value is invalid."},
    500: {"description": "Stored Story Bible data is inconsistent."},
    503: {"description": "Story Bible persistence or service is unavailable."},
}
_REVISE_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The If-Match header is malformed."},
    403: {"description": "A trusted local session and CSRF context are required."},
    404: {"description": "Story Bible not found."},
    412: {"description": "The supplied Story Bible version is stale."},
    413: {"description": "The request body exceeds one MiB."},
    415: {"description": "A JSON media type is required."},
    422: {"description": "The request or a Story Bible value is invalid."},
    428: {"description": "If-Match is required."},
    500: {"description": "Stored Story Bible data is inconsistent."},
    503: {"description": "Story Bible persistence or service is unavailable."},
}


def _set_story_bible_headers(
    response: Response,
    story_bible: StoryBibleResponse,
) -> None:
    response.headers["ETag"] = format_strong_etag(story_bible.concurrency_version)
    response.headers["Cache-Control"] = "no-store"


def create_story_bible_router(*, api_prefix: str) -> APIRouter:
    """Create the versioned Story Bible router without touching persistence."""
    router = APIRouter(prefix=api_prefix, tags=["Story Bible"])

    @router.post(
        "/projects/{project_id}/story-bible",
        response_model=StoryBibleResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_CREATE_RESPONSES,
        summary="Create a Project's Story Bible",
        description=(
            "Creates the Project's single allowed Story Bible and its initial immutable "
            "revision. A trusted local Session, same-origin request, and CSRF token are "
            "required. The strong ETag represents ConcurrencyVersion. Revision history, "
            "delete, archive, and restore operations are not exposed."
        ),
    )
    def create_story_bible(
        response: Response,
        project_id: Annotated[str, Depends(get_story_bible_project_id)],
        _json_content_type: Annotated[None, Depends(require_story_bible_json)],
        payload: CreateStoryBibleRequest,
        service: Annotated[
            StoryBibleCommandService,
            Depends(get_story_bible_command_service),
        ],
    ) -> StoryBibleResponse:
        command = create_story_bible_command_from_request(project_id, payload)
        try:
            snapshot = service.create_story_bible(command)
        except DomainError as exc:
            raise_story_bible_http_error(exc)
        result = story_bible_response_from_snapshot(snapshot)
        _set_story_bible_headers(response, result)
        response.headers["Location"] = f"{api_prefix}/story-bibles/{result.story_bible_id}"
        return result

    @router.get(
        "/projects/{project_id}/story-bible",
        response_model=StoryBibleResponse,
        responses=_READ_RESPONSES,
        summary="Get a Project's current Story Bible",
        description=(
            "Returns only the Project-owned current Story Bible snapshot. "
            "Session, CSRF, and Origin are not required for this read. Revision history, "
            "delete, archive, and restore operations are intentionally not exposed."
        ),
    )
    def get_story_bible_for_project(
        response: Response,
        project_id: Annotated[str, Depends(get_story_bible_project_id)],
        service: Annotated[
            StoryBibleQueryService,
            Depends(get_story_bible_query_service),
        ],
    ) -> StoryBibleResponse:
        try:
            snapshot = service.get_story_bible_for_project(
                GetStoryBibleForProjectQuery(project_id=project_id)
            )
        except DomainError as exc:
            raise_story_bible_http_error(exc)
        result = story_bible_response_from_snapshot(snapshot)
        _set_story_bible_headers(response, result)
        return result

    @router.get(
        "/story-bibles/{story_bible_id}",
        response_model=StoryBibleResponse,
        responses=_READ_RESPONSES,
        summary="Get a current Story Bible",
        description=(
            "Returns one current Story Bible snapshot by stable identifier. "
            "Session, CSRF, and Origin are not required for this read. Revision history, "
            "delete, archive, and restore operations are intentionally not exposed."
        ),
    )
    def get_story_bible(
        response: Response,
        story_bible_id: Annotated[str, Depends(get_story_bible_id)],
        service: Annotated[
            StoryBibleQueryService,
            Depends(get_story_bible_query_service),
        ],
    ) -> StoryBibleResponse:
        try:
            snapshot = service.get_story_bible(GetStoryBibleQuery(story_bible_id=story_bible_id))
        except DomainError as exc:
            raise_story_bible_http_error(exc)
        result = story_bible_response_from_snapshot(snapshot)
        _set_story_bible_headers(response, result)
        return result

    @router.put(
        "/story-bibles/{story_bible_id}",
        response_model=StoryBibleResponse,
        responses=_REVISE_RESPONSES,
        summary="Completely revise a Story Bible",
        description=(
            "Completely replaces title and content; PATCH is intentionally unsupported. "
            "A trusted local Session, same-origin request, and CSRF token are required. "
            "If-Match must contain the current strong version ETag. Revision history, "
            "delete, archive, and restore operations are not exposed."
        ),
        openapi_extra={
            "parameters": [
                {
                    "name": "If-Match",
                    "in": "header",
                    "required": True,
                    "description": 'Required strong Story Bible ETag, for example "1".',
                    "schema": {"type": "string"},
                }
            ]
        },
    )
    def revise_story_bible(
        response: Response,
        story_bible_id: Annotated[str, Depends(get_story_bible_id)],
        _json_content_type: Annotated[None, Depends(require_story_bible_json)],
        payload: ReviseStoryBibleRequest,
        expected_version: Annotated[
            ConcurrencyVersion,
            Depends(get_required_story_bible_version),
        ],
        service: Annotated[
            StoryBibleCommandService,
            Depends(get_story_bible_command_service),
        ],
    ) -> StoryBibleResponse:
        command = revise_story_bible_command_from_request(
            story_bible_id,
            int(expected_version),
            payload,
        )
        try:
            snapshot = service.revise_story_bible(command)
        except DomainError as exc:
            raise_story_bible_http_error(exc)
        result = story_bible_response_from_snapshot(snapshot)
        _set_story_bible_headers(response, result)
        return result

    return router


__all__ = ["create_story_bible_router"]
