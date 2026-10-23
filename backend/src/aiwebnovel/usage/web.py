"""Read-only usage ledger HTTP contract; viewing usage never calls a model."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import InvalidDomainIdentifier
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.usage.models import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, UsagePage
from aiwebnovel.usage.service import UsageLedgerService

_MAX_OFFSET = 1_000_000
_ALLOWED = frozenset({"chapter_id", "task_id", "offset", "limit"})


def get_usage_service(request: Request) -> UsageLedgerService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            message="Back up and explicitly upgrade the database to view model usage.",
            status_code=503,
        )
    service = getattr(request.app.state, "usage_ledger_service", None)
    if not isinstance(service, UsageLedgerService):
        raise AppError(
            code="USAGE_LEDGER_UNAVAILABLE",
            message="The model usage ledger is unavailable.",
            status_code=503,
        )
    return service


def _invalid_query() -> AppError:
    return AppError(
        code="INVALID_USAGE_QUERY",
        message="The usage query parameters are invalid.",
        status_code=422,
    )


def _single(request: Request, name: str) -> str | None:
    values = request.query_params.getlist(name)
    if len(values) > 1:
        raise _invalid_query()
    return values[0] if values else None


def _integer(request: Request, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = _single(request, name)
    if raw is None:
        return default
    if not raw or len(raw) > 7 or not raw.isascii() or not raw.isdecimal():
        raise _invalid_query()
    value = int(raw, 10)
    if not minimum <= value <= maximum:
        raise _invalid_query()
    return value


def get_usage_query(request: Request) -> tuple[str | None, str | None, int, int]:
    if any(key not in _ALLOWED for key in request.query_params):
        raise _invalid_query()
    chapter_id = _single(request, "chapter_id")
    task_id = _single(request, "task_id")
    if (chapter_id is not None and not 1 <= len(chapter_id) <= 60) or (
        task_id is not None
        and (
            not 1 <= len(task_id) <= 36
            or not task_id.isascii()
            or not all(char.isalnum() or char in "-_" for char in task_id)
        )
    ):
        raise _invalid_query()
    return (
        chapter_id,
        task_id,
        _integer(request, "offset", 0, 0, _MAX_OFFSET),
        _integer(request, "limit", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE),
    )


Service = Annotated[UsageLedgerService, Depends(get_usage_service)]
Query = Annotated[tuple[str | None, str | None, int, int], Depends(get_usage_query)]


def create_usage_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["Model Usage"])

    @router.get("/projects/{project_id}/usage", response_model=UsagePage)
    def project_usage(
        project_id: str, response: Response, service: Service, query: Query
    ) -> UsagePage:
        response.headers["Cache-Control"] = "no-store"
        chapter_id, task_id, offset, limit = query
        try:
            return service.project_usage(
                project_id, chapter_id=chapter_id, task_id=task_id, offset=offset, limit=limit
            )
        except InvalidDomainIdentifier:
            raise AppError(
                code="INVALID_USAGE_QUERY",
                message="The Project or Chapter identifier is invalid.",
                status_code=422,
            ) from None
        except ProjectNotFound:
            raise AppError(
                code="PROJECT_NOT_FOUND", message="Project not found.", status_code=404
            ) from None

    return router
