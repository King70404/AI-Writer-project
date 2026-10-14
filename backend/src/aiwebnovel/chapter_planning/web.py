"""Chapter planning HTTP operations protected by the shared application boundary."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from aiwebnovel.ai_writing.web import map_error, require_json
from aiwebnovel.chapter_planning.models import (
    ChapterPlan,
    PlanningConflict,
    PlanningReferenceInvalid,
    SaveChapterPlan,
)
from aiwebnovel.chapter_planning.service import ChapterPlanningService
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError


def get_planning_service(request: Request) -> ChapterPlanningService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            message="Back up and explicitly upgrade the database to use chapter planning.",
            status_code=503,
        )
    service = getattr(request.app.state, "chapter_planning_service", None)
    if not isinstance(service, ChapterPlanningService):
        raise AppError(
            code="PLANNING_UNAVAILABLE",
            message="Chapter planning is unavailable.",
            status_code=503,
        )
    return service


def _invoke[T](response: Response, action: Callable[[], T]) -> T:
    response.headers["Cache-Control"] = "no-store"
    try:
        return action()
    except PlanningConflict:
        raise AppError(
            code="PLANNING_CONFLICT", message=PlanningConflict.message, status_code=409
        ) from None
    except PlanningReferenceInvalid:
        raise AppError(
            code="PLANNING_REFERENCE_INVALID",
            message=PlanningReferenceInvalid.message,
            status_code=422,
        ) from None
    except DomainError as error:
        raise map_error(error) from None


Service = Annotated[ChapterPlanningService, Depends(get_planning_service)]


def create_chapter_planning_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(
        prefix=api_prefix + "/chapters/{chapter_id}/planning", tags=["Chapter Planning"]
    )

    @router.get("", response_model=ChapterPlan | None)
    def get(chapter_id: str, response: Response, service: Service) -> ChapterPlan | None:
        return _invoke(response, lambda: service.get(chapter_id))

    @router.put("", response_model=ChapterPlan)
    def save(
        chapter_id: str,
        payload: SaveChapterPlan,
        response: Response,
        service: Service,
        _json: Annotated[None, Depends(require_json)],
    ) -> ChapterPlan:
        return _invoke(response, lambda: service.save(chapter_id, payload))

    return router
