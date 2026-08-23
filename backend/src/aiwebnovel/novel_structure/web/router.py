"""The eleven intentionally bounded novel-structure HTTP operations."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from aiwebnovel.api.etags import format_strong_etag
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.application.queries import (
    GetChapterQuery,
    GetOutlineForProjectQuery,
    GetVolumeQuery,
    ListChaptersQuery,
    ListVolumesQuery,
)
from aiwebnovel.novel_structure.application.services import (
    NovelStructureCommandService,
    NovelStructureQueryService,
)
from aiwebnovel.novel_structure.errors import ChapterVolumeOwnershipMismatch
from aiwebnovel.novel_structure.web.dependencies import (
    get_chapter_id,
    get_command_service,
    get_outline_id,
    get_project_id,
    get_query_service,
    get_required_version,
    get_volume_id,
    require_json,
)
from aiwebnovel.novel_structure.web.dto import (
    ChapterResponse,
    CreateChapterRequest,
    CreateOutlineRequest,
    CreateVolumeRequest,
    OutlineResponse,
    UpdateChapterRequest,
    UpdateOutlineRequest,
    UpdateVolumeRequest,
    VolumeResponse,
)
from aiwebnovel.novel_structure.web.errors import raise_novel_structure_http_error
from aiwebnovel.novel_structure.web.mappers import (
    chapter_response,
    create_chapter_command,
    create_outline_command,
    create_volume_command,
    outline_response,
    update_chapter_command,
    update_outline_command,
    update_volume_command,
    volume_response,
)

_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "The requested Project or structure resource was not found."},
    422: {"description": "A path identifier is invalid."},
    500: {"description": "Stored novel-structure data is inconsistent."},
    503: {"description": "Novel-structure persistence or service is unavailable."},
}
_LIST_RESPONSES = _READ_RESPONSES
_CREATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"description": "A trusted local session and CSRF context are required."},
    404: {"description": "The owning Project or Volume was not found."},
    409: {"description": "The identity, ownership, or position conflicts."},
    413: {"description": "The request body exceeds one MiB."},
    415: {"description": "A JSON media type is required."},
    422: {"description": "The request or a novel-structure value is invalid."},
    500: {"description": "Stored novel-structure data is inconsistent."},
    503: {"description": "Novel-structure persistence or service is unavailable."},
}
_UPDATE_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The If-Match header is malformed."},
    403: {"description": "A trusted local session and CSRF context are required."},
    404: {"description": "The requested structure resource was not found."},
    409: {"description": "The requested position conflicts."},
    412: {"description": "The supplied resource version is stale."},
    413: {"description": "The request body exceeds one MiB."},
    415: {"description": "A JSON media type is required."},
    422: {"description": "The request or a novel-structure value is invalid."},
    428: {"description": "If-Match is required."},
    500: {"description": "Stored novel-structure data is inconsistent."},
    503: {"description": "Novel-structure persistence or service is unavailable."},
}
_IF_MATCH_OPENAPI: dict[str, Any] = {
    "parameters": [
        {
            "name": "If-Match",
            "in": "header",
            "required": True,
            "description": 'Required strong resource ETag, for example "1".',
            "schema": {"type": "string"},
        }
    ]
}


def _set_current_headers(response: Response, version: int) -> None:
    response.headers["ETag"] = format_strong_etag(version)
    response.headers["Cache-Control"] = "no-store"


def _set_list_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def create_novel_structure_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["Novel Structure"])

    @router.post(
        "/projects/{project_id}/outline",
        response_model=OutlineResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_CREATE_RESPONSES,
        summary="Create a Project Outline",
    )
    def create_outline(
        response: Response,
        project_id: Annotated[str, Depends(get_project_id)],
        _json: Annotated[None, Depends(require_json)],
        payload: CreateOutlineRequest,
        service: Annotated[NovelStructureCommandService, Depends(get_command_service)],
    ) -> OutlineResponse:
        try:
            snapshot = service.create_outline(create_outline_command(project_id, payload))
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="outline")
        result = outline_response(snapshot)
        _set_current_headers(response, result.concurrency_version)
        response.headers["Location"] = f"{api_prefix}/projects/{project_id}/outline"
        return result

    @router.get(
        "/projects/{project_id}/outline",
        response_model=OutlineResponse,
        responses=_READ_RESPONSES,
        summary="Get a Project's current Outline",
    )
    def get_outline_for_project(
        response: Response,
        project_id: Annotated[str, Depends(get_project_id)],
        service: Annotated[NovelStructureQueryService, Depends(get_query_service)],
    ) -> OutlineResponse:
        try:
            snapshot = service.get_outline_for_project(
                GetOutlineForProjectQuery(project_id=project_id)
            )
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="outline")
        result = outline_response(snapshot)
        _set_current_headers(response, result.concurrency_version)
        return result

    @router.put(
        "/outlines/{outline_id}",
        response_model=OutlineResponse,
        responses=_UPDATE_RESPONSES,
        summary="Completely update an Outline",
        openapi_extra=_IF_MATCH_OPENAPI,
    )
    def update_outline(
        response: Response,
        outline_id: Annotated[str, Depends(get_outline_id)],
        _json: Annotated[None, Depends(require_json)],
        payload: UpdateOutlineRequest,
        expected: Annotated[ConcurrencyVersion, Depends(get_required_version)],
        service: Annotated[NovelStructureCommandService, Depends(get_command_service)],
    ) -> OutlineResponse:
        try:
            snapshot = service.update_outline(
                update_outline_command(outline_id, int(expected), payload)
            )
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="outline")
        result = outline_response(snapshot)
        _set_current_headers(response, result.concurrency_version)
        return result

    @router.post(
        "/projects/{project_id}/volumes",
        response_model=VolumeResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_CREATE_RESPONSES,
        summary="Create a Project Volume",
    )
    def create_volume(
        response: Response,
        project_id: Annotated[str, Depends(get_project_id)],
        _json: Annotated[None, Depends(require_json)],
        payload: CreateVolumeRequest,
        service: Annotated[NovelStructureCommandService, Depends(get_command_service)],
    ) -> VolumeResponse:
        try:
            snapshot = service.create_volume(create_volume_command(project_id, payload))
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="volume")
        result = volume_response(snapshot)
        _set_current_headers(response, result.concurrency_version)
        response.headers["Location"] = f"{api_prefix}/volumes/{result.volume_id}"
        return result

    @router.get(
        "/projects/{project_id}/volumes",
        response_model=tuple[VolumeResponse, ...],
        responses=_LIST_RESPONSES,
        summary="List a Project's current Volumes",
    )
    def list_volumes(
        response: Response,
        project_id: Annotated[str, Depends(get_project_id)],
        service: Annotated[NovelStructureQueryService, Depends(get_query_service)],
    ) -> tuple[VolumeResponse, ...]:
        try:
            snapshots = service.list_volumes(ListVolumesQuery(project_id=project_id))
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="volume")
        _set_list_headers(response)
        return tuple(volume_response(snapshot) for snapshot in snapshots)

    @router.get(
        "/volumes/{volume_id}",
        response_model=VolumeResponse,
        responses=_READ_RESPONSES,
        summary="Get a current Volume",
    )
    def get_volume(
        response: Response,
        volume_id: Annotated[str, Depends(get_volume_id)],
        service: Annotated[NovelStructureQueryService, Depends(get_query_service)],
    ) -> VolumeResponse:
        try:
            snapshot = service.get_volume(GetVolumeQuery(volume_id=volume_id))
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="volume")
        result = volume_response(snapshot)
        _set_current_headers(response, result.concurrency_version)
        return result

    @router.put(
        "/volumes/{volume_id}",
        response_model=VolumeResponse,
        responses=_UPDATE_RESPONSES,
        summary="Completely update a Volume",
        openapi_extra=_IF_MATCH_OPENAPI,
    )
    def update_volume(
        response: Response,
        volume_id: Annotated[str, Depends(get_volume_id)],
        _json: Annotated[None, Depends(require_json)],
        payload: UpdateVolumeRequest,
        expected: Annotated[ConcurrencyVersion, Depends(get_required_version)],
        service: Annotated[NovelStructureCommandService, Depends(get_command_service)],
    ) -> VolumeResponse:
        try:
            snapshot = service.update_volume(
                update_volume_command(volume_id, int(expected), payload)
            )
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="volume")
        result = volume_response(snapshot)
        _set_current_headers(response, result.concurrency_version)
        return result

    @router.post(
        "/projects/{project_id}/volumes/{volume_id}/chapters",
        response_model=ChapterResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_CREATE_RESPONSES,
        summary="Create a Chapter in a Project Volume",
    )
    def create_chapter(
        response: Response,
        project_id: Annotated[str, Depends(get_project_id)],
        volume_id: Annotated[str, Depends(get_volume_id)],
        _json: Annotated[None, Depends(require_json)],
        payload: CreateChapterRequest,
        service: Annotated[NovelStructureCommandService, Depends(get_command_service)],
    ) -> ChapterResponse:
        try:
            snapshot = service.create_chapter(
                create_chapter_command(project_id, volume_id, payload)
            )
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="chapter")
        result = chapter_response(snapshot)
        _set_current_headers(response, result.concurrency_version)
        response.headers["Location"] = f"{api_prefix}/chapters/{result.chapter_id}"
        return result

    @router.get(
        "/projects/{project_id}/volumes/{volume_id}/chapters",
        response_model=tuple[ChapterResponse, ...],
        responses=_LIST_RESPONSES,
        summary="List current Chapters in a Project Volume",
    )
    def list_chapters(
        response: Response,
        project_id: Annotated[str, Depends(get_project_id)],
        volume_id: Annotated[str, Depends(get_volume_id)],
        service: Annotated[NovelStructureQueryService, Depends(get_query_service)],
    ) -> tuple[ChapterResponse, ...]:
        try:
            volume = service.get_volume(GetVolumeQuery(volume_id=volume_id))
            if volume.project_id != project_id:
                raise ChapterVolumeOwnershipMismatch
            snapshots = service.list_chapters(ListChaptersQuery(volume_id=volume_id))
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="chapter")
        _set_list_headers(response)
        return tuple(chapter_response(snapshot) for snapshot in snapshots)

    @router.get(
        "/chapters/{chapter_id}",
        response_model=ChapterResponse,
        responses=_READ_RESPONSES,
        summary="Get a current Chapter",
    )
    def get_chapter(
        response: Response,
        chapter_id: Annotated[str, Depends(get_chapter_id)],
        service: Annotated[NovelStructureQueryService, Depends(get_query_service)],
    ) -> ChapterResponse:
        try:
            snapshot = service.get_chapter(GetChapterQuery(chapter_id=chapter_id))
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="chapter")
        result = chapter_response(snapshot)
        _set_current_headers(response, result.concurrency_version)
        return result

    @router.put(
        "/chapters/{chapter_id}",
        response_model=ChapterResponse,
        responses=_UPDATE_RESPONSES,
        summary="Completely update a Chapter",
        openapi_extra=_IF_MATCH_OPENAPI,
    )
    def update_chapter(
        response: Response,
        chapter_id: Annotated[str, Depends(get_chapter_id)],
        _json: Annotated[None, Depends(require_json)],
        payload: UpdateChapterRequest,
        expected: Annotated[ConcurrencyVersion, Depends(get_required_version)],
        service: Annotated[NovelStructureCommandService, Depends(get_command_service)],
    ) -> ChapterResponse:
        try:
            snapshot = service.update_chapter(
                update_chapter_command(chapter_id, int(expected), payload)
            )
        except DomainError as exc:
            raise_novel_structure_http_error(exc, resource="chapter")
        result = chapter_response(snapshot)
        _set_current_headers(response, result.concurrency_version)
        return result

    return router


__all__ = ["create_novel_structure_router"]
