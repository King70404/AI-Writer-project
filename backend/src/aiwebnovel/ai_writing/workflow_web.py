"""Persistent AI workflow routes behind the application's existing session/CSRF guards."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.ai_writing.application.workflow import AIWorkflowService
from aiwebnovel.ai_writing.application.workflow_models import (
    CandidateEdit,
    CandidateEditInvalid,
    WorkflowConflict,
    WorkflowNotFound,
    WorkflowOutputInvalid,
    WorkflowRun,
)
from aiwebnovel.ai_writing.web import map_error, require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict, DomainError
from aiwebnovel.model_gateway.errors import (
    InvalidModelProfile,
    ModelConfigurationUnavailable,
    ModelCredentialUnavailable,
    ModelProfileNotFound,
)
from aiwebnovel.model_gateway.web import map_model_error
from aiwebnovel.novel_structure.web.dependencies import get_required_version
from aiwebnovel.usage.budget import SendEstimate


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CreateRunRequest(EmptyRequest):
    operation: Literal["continue", "rewrite"] = "continue"
    instruction: str = Field(default="", max_length=4000)
    profile_id: str | None = Field(default=None, max_length=100)
    selected_text: str = Field(default="", max_length=50_000)
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=1)
    max_steps: int = Field(default=5, ge=1, le=10)
    max_output_characters: int = Field(default=1500, ge=200, le=3000)


class AdoptRequest(EmptyRequest):
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    # The author edit to adopt instead of the model's original text; must be the newest.
    edit_id: str | None = Field(default=None, min_length=36, max_length=36)


class CreateEditRequest(EmptyRequest):
    text: str = Field(min_length=1, max_length=12_000)
    # The newest edit this one replaces (``None`` for the first); a stale parent conflicts.
    parent_edit_id: str | None = Field(default=None, min_length=36, max_length=36)


def get_workflow_service(request: Request) -> AIWorkflowService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            message="Back up and explicitly upgrade the database to use AI collaboration.",
            status_code=503,
        )
    service = getattr(request.app.state, "ai_workflow_service", None)
    if not isinstance(service, AIWorkflowService):
        raise AppError(
            code="AI_SERVICE_UNAVAILABLE",
            message="AI workflow service is unavailable.",
            status_code=503,
        )
    return service


def _invoke[T](response: Response, call: Callable[[], T]) -> T:
    response.headers["Cache-Control"] = "no-store"
    try:
        return call()
    except DomainError as error:
        if isinstance(
            error,
            (
                InvalidModelProfile,
                ModelConfigurationUnavailable,
                ModelCredentialUnavailable,
                ModelProfileNotFound,
            ),
        ):
            raise map_model_error(error) from None
        if isinstance(error, WorkflowConflict):
            raise AppError(
                code="AI_WORKFLOW_CONFLICT", message=error.message, status_code=409
            ) from None
        if isinstance(error, WorkflowNotFound):
            raise AppError(
                code="AI_WORKFLOW_NOT_FOUND", message=error.message, status_code=404
            ) from None
        if isinstance(error, CandidateEditInvalid):
            raise AppError(
                code="AI_CANDIDATE_EDIT_INVALID", message=error.message, status_code=422
            ) from None
        if isinstance(error, WorkflowOutputInvalid):
            raise AppError(
                code="AI_OUTPUT_LENGTH_INVALID", message=error.message, status_code=502
            ) from None
        if isinstance(error, ConcurrencyConflict):
            raise AppError(
                code="CONCURRENCY_CONFLICT",
                message="The Chapter changed. Refresh before adopting.",
                status_code=409,
            ) from None
        raise map_error(error) from None


Service = Annotated[AIWorkflowService, Depends(get_workflow_service)]
Json = Annotated[None, Depends(require_json)]


def create_ai_workflow_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix + "/chapters/{chapter_id}/ai", tags=["AI Workflows"])

    @router.post("/runs", response_model=WorkflowRun, status_code=201)
    def create_run(
        chapter_id: str,
        payload: CreateRunRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WorkflowRun:
        return _invoke(response, lambda: service.create(chapter_id, **payload.model_dump()))

    @router.get("/runs", response_model=tuple[WorkflowRun, ...])
    def list_runs(chapter_id: str, response: Response, service: Service) -> tuple[WorkflowRun, ...]:
        return _invoke(response, lambda: service.list(chapter_id))

    @router.get("/runs/{run_id}", response_model=WorkflowRun)
    def get_run(chapter_id: str, run_id: str, response: Response, service: Service) -> WorkflowRun:
        return _invoke(response, lambda: service.get(chapter_id, run_id))

    @router.post("/runs/{run_id}/generate", response_model=WorkflowRun)
    def generate(
        chapter_id: str,
        run_id: str,
        payload: EmptyRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WorkflowRun:
        return _invoke(response, lambda: service.generate(chapter_id, run_id))

    @router.post("/runs/{run_id}/pause", response_model=WorkflowRun)
    def pause(
        chapter_id: str,
        run_id: str,
        payload: EmptyRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WorkflowRun:
        return _invoke(response, lambda: service.pause(chapter_id, run_id))

    @router.post("/runs/{run_id}/resume", response_model=WorkflowRun)
    def resume(
        chapter_id: str,
        run_id: str,
        payload: EmptyRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WorkflowRun:
        return _invoke(response, lambda: service.resume(chapter_id, run_id))

    @router.post("/candidates/{candidate_id}/adopt", response_model=WorkflowRun)
    def adopt(
        chapter_id: str,
        candidate_id: str,
        payload: AdoptRequest,
        response: Response,
        service: Service,
        _json: Json,
        version: Annotated[ConcurrencyVersion, Depends(get_required_version)],
    ) -> WorkflowRun:
        return _invoke(
            response,
            lambda: service.adopt(
                chapter_id,
                candidate_id,
                int(version),
                payload.idempotency_key,
                payload.edit_id,
            ),
        )

    @router.post("/candidates/{candidate_id}/edits", response_model=WorkflowRun, status_code=201)
    def create_edit(
        chapter_id: str,
        candidate_id: str,
        payload: CreateEditRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WorkflowRun:
        return _invoke(
            response,
            lambda: service.edit_candidate(
                chapter_id, candidate_id, payload.text, payload.parent_edit_id
            ),
        )

    @router.get("/candidates/{candidate_id}/edits", response_model=tuple[CandidateEdit, ...])
    def list_edits(
        chapter_id: str, candidate_id: str, response: Response, service: Service
    ) -> tuple[CandidateEdit, ...]:
        return _invoke(response, lambda: service.candidate_edits(chapter_id, candidate_id))

    @router.get("/runs/{run_id}/estimate", response_model=SendEstimate)
    def estimate(
        chapter_id: str, run_id: str, response: Response, service: Service
    ) -> SendEstimate:
        return _invoke(response, lambda: service.estimate(chapter_id, run_id))

    @router.post("/candidates/{candidate_id}/discard", response_model=WorkflowRun)
    def discard(
        chapter_id: str,
        candidate_id: str,
        payload: EmptyRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WorkflowRun:
        return _invoke(response, lambda: service.discard(chapter_id, candidate_id))

    return router
