"""Workbench HTTP reads and the author-only editorial-state command."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from aiwebnovel.ai_writing.web import map_error, require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError, InvalidDomainIdentifier
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.workbench.models import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ActionPage,
    BookshelfPage,
    ChapterSummaryPage,
    EditorialConflict,
    EditorialState,
    SaveEditorialState,
    WorkspaceSummary,
)
from aiwebnovel.workbench.service import WorkbenchService, WorkbenchVolumeNotFound

_MAX_OFFSET = 1_000_000


def get_workbench_service(request: Request) -> WorkbenchService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            message="Back up and explicitly upgrade the database to use the workbench summary.",
            status_code=503,
        )
    service = getattr(request.app.state, "workbench_service", None)
    if not isinstance(service, WorkbenchService):
        raise AppError(
            code="WORKBENCH_UNAVAILABLE",
            message="The workbench summary is unavailable.",
            status_code=503,
        )
    return service


def _invalid_query() -> AppError:
    return AppError(
        code="INVALID_WORKBENCH_QUERY",
        message="The workbench page parameters are invalid.",
        status_code=422,
    )


def _project_call[T](response: Response, action: Callable[[], T]) -> T:
    response.headers["Cache-Control"] = "no-store"
    try:
        return action()
    except InvalidDomainIdentifier:
        raise AppError(
            code="INVALID_PROJECT_ID", message="The Project identifier is invalid.", status_code=422
        ) from None
    except ProjectNotFound:
        raise AppError(
            code="PROJECT_NOT_FOUND", message="Project not found.", status_code=404
        ) from None
    except WorkbenchVolumeNotFound:
        raise AppError(
            code="VOLUME_NOT_FOUND", message=WorkbenchVolumeNotFound.message, status_code=404
        ) from None


def _chapter_call[T](response: Response, action: Callable[[], T]) -> T:
    response.headers["Cache-Control"] = "no-store"
    try:
        return action()
    except EditorialConflict:
        raise AppError(
            code="EDITORIAL_CONFLICT", message=EditorialConflict.message, status_code=409
        ) from None
    except DomainError as error:
        raise map_error(error) from None


def _integer(request: Request, name: str, default: int, maximum: int, minimum: int) -> int:
    values = request.query_params.getlist(name)
    if not values:
        return default
    raw = values[0]
    if len(values) > 1 or not raw or len(raw) > 7 or not raw.isascii() or not raw.isdecimal():
        raise _invalid_query()
    value = int(raw, 10)
    if not minimum <= value <= maximum:
        raise _invalid_query()
    return value


def _page(request: Request, allowed: frozenset[str]) -> tuple[int, int]:
    if any(key not in allowed for key in request.query_params):
        raise _invalid_query()
    return (
        _integer(request, "offset", 0, _MAX_OFFSET, 0),
        _integer(request, "limit", DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, 1),
    )


def get_chapter_page(request: Request) -> tuple[str | None, int, int]:
    offset, limit = _page(request, frozenset({"volume_id", "offset", "limit"}))
    volumes = request.query_params.getlist("volume_id")
    if len(volumes) > 1 or (volumes and not 1 <= len(volumes[0]) <= 60):
        raise _invalid_query()
    return (volumes[0] if volumes else None, offset, limit)


def get_action_page(request: Request) -> tuple[int, int]:
    return _page(request, frozenset({"offset", "limit"}))


Service = Annotated[WorkbenchService, Depends(get_workbench_service)]


def create_workbench_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["Author Workbench"])

    @router.get("/workspace/overview", response_model=BookshelfPage | None)
    def overview(
        request: Request,
        response: Response,
        page: Annotated[tuple[int, int], Depends(get_action_page)],
    ) -> BookshelfPage | None:
        response.headers["Cache-Control"] = "no-store"
        # A healthy foundation database may not have author-workflow tables yet.
        # Signal unavailable explicitly; never invent an empty bookshelf.
        service = getattr(request.app.state, "workbench_service", None)
        if getattr(request.app.state, "ai_workflow_schema_required", False) or not isinstance(
            service, WorkbenchService
        ):
            return None
        return service.overview(*page)

    @router.get("/projects/{project_id}/workspace", response_model=WorkspaceSummary)
    def summary(project_id: str, response: Response, service: Service) -> WorkspaceSummary:
        return _project_call(response, lambda: service.summary(project_id))

    @router.get("/projects/{project_id}/workspace/chapters", response_model=ChapterSummaryPage)
    def chapters(
        project_id: str,
        response: Response,
        service: Service,
        page: Annotated[tuple[str | None, int, int], Depends(get_chapter_page)],
    ) -> ChapterSummaryPage:
        return _project_call(response, lambda: service.chapters(project_id, *page))

    @router.get(
        "/projects/{project_id}/workspace/actions",
        response_model=ActionPage,
        response_model_exclude_defaults=True,
    )
    def actions(
        project_id: str,
        response: Response,
        service: Service,
        page: Annotated[tuple[int, int], Depends(get_action_page)],
    ) -> ActionPage:
        return _project_call(response, lambda: service.actions(project_id, *page))

    @router.get("/chapters/{chapter_id}/editorial-state", response_model=EditorialState)
    def editorial(chapter_id: str, response: Response, service: Service) -> EditorialState:
        return _chapter_call(response, lambda: service.editorial_state(chapter_id))

    @router.put("/chapters/{chapter_id}/editorial-state", response_model=EditorialState)
    def save_editorial(
        chapter_id: str,
        payload: SaveEditorialState,
        response: Response,
        service: Service,
        _json: Annotated[None, Depends(require_json)],
    ) -> EditorialState:
        return _chapter_call(
            response,
            lambda: service.save_editorial_state(
                chapter_id, payload.status, payload.expected_version
            ),
        )

    return router
