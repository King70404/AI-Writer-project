"""Chapter manuscript HTTP subresource backed only by application services."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from aiwebnovel.api.etags import format_strong_etag
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.application.queries import GetChapterContentQuery
from aiwebnovel.novel_structure.application.services import (
    NovelStructureCommandService,
    NovelStructureQueryService,
)
from aiwebnovel.novel_structure.web.dependencies import (
    get_chapter_id,
    get_command_service,
    get_query_service,
    get_required_version,
    require_json,
)
from aiwebnovel.novel_structure.web.dto import (
    ChapterContentResponse,
    UpdateChapterContentRequest,
)
from aiwebnovel.novel_structure.web.errors import raise_novel_structure_http_error
from aiwebnovel.novel_structure.web.mappers import (
    chapter_content_response,
    update_chapter_content_command,
)

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "The requested Chapter was not found."},
    422: {"description": "The Chapter identifier is invalid."},
    500: {"description": "Stored Chapter data is inconsistent."},
    503: {"description": "Chapter persistence or service is unavailable."},
}
_UPDATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The If-Match header is malformed."},
    403: {"description": "A trusted local session and CSRF context are required."},
    404: {"description": "The requested Chapter was not found."},
    412: {"description": "The supplied Chapter version is stale."},
    413: {"description": "The request body exceeds the configured limit."},
    415: {"description": "A JSON media type is required."},
    422: {"description": "The request or manuscript content is invalid."},
    428: {"description": "If-Match is required."},
    500: {"description": "Stored Chapter data is inconsistent."},
    503: {"description": "Chapter persistence or service is unavailable."},
}
_IF_MATCH_OPENAPI: dict[str, Any] = {
    "parameters": [
        {
            "name": "If-Match",
            "in": "header",
            "required": True,
            "description": 'Required strong Chapter ETag, for example "1".',
            "schema": {"type": "string"},
        }
    ]
}


def _set_content_headers(response: Response, version: int) -> None:
    response.headers["ETag"] = format_strong_etag(version)
    response.headers["Cache-Control"] = "no-store"


def create_chapter_content_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["Chapter Writing"])

    @router.get(
        "/chapters/{chapter_id}/content",
        response_model=ChapterContentResponse,
        responses=_READ_RESPONSES,
        summary="Get current Chapter manuscript content",
    )
    def get_chapter_content(
        response: Response,
        chapter_id: Annotated[str, Depends(get_chapter_id)],
        service: Annotated[NovelStructureQueryService, Depends(get_query_service)],
    ) -> ChapterContentResponse:
        try:
            snapshot = service.get_chapter_content(GetChapterContentQuery(chapter_id=chapter_id))
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="chapter")
        result = chapter_content_response(snapshot)
        _set_content_headers(response, result.concurrency_version)
        return result

    @router.put(
        "/chapters/{chapter_id}/content",
        response_model=ChapterContentResponse,
        responses=_UPDATE_RESPONSES,
        summary="Completely replace Chapter manuscript content",
        openapi_extra=_IF_MATCH_OPENAPI,
    )
    def update_chapter_content(
        response: Response,
        chapter_id: Annotated[str, Depends(get_chapter_id)],
        _json: Annotated[None, Depends(require_json)],
        payload: UpdateChapterContentRequest,
        expected: Annotated[ConcurrencyVersion, Depends(get_required_version)],
        service: Annotated[NovelStructureCommandService, Depends(get_command_service)],
    ) -> ChapterContentResponse:
        try:
            snapshot = service.update_chapter_content(
                update_chapter_content_command(chapter_id, int(expected), payload)
            )
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="chapter")
        result = chapter_content_response(snapshot)
        _set_content_headers(response, result.concurrency_version)
        return result

    return router


__all__ = ["create_chapter_content_router"]
