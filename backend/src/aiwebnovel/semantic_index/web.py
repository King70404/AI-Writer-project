"""Semantic index HTTP: status/plan reads never call a model; building needs confirmation."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from aiwebnovel.ai_writing.web import map_error, require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError, InvalidDomainIdentifier
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.semantic_index.models import (
    BuildInput,
    BuildResult,
    IndexStatus,
    SemanticIndexConfirmationRequired,
    SemanticIndexConflict,
    SemanticIndexInvalid,
    SemanticIndexNothingToDo,
    SettingsInput,
    SettingsView,
)
from aiwebnovel.semantic_index.service import SemanticIndexService


def get_semantic_index_service(request: Request) -> SemanticIndexService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            message="Explicit backup and upgrade required.",
            status_code=503,
        )
    memory = getattr(request.app.state, "story_memory_service", None)
    service = getattr(memory, "semantic_index", None)
    if not isinstance(service, SemanticIndexService):
        raise AppError(
            code="SEMANTIC_INDEX_UNAVAILABLE",
            message="The semantic index is unavailable.",
            status_code=503,
        )
    return service


_ERRORS: dict[type[DomainError], tuple[int, str]] = {
    SemanticIndexInvalid: (422, "SEMANTIC_INDEX_INVALID"),
    SemanticIndexConflict: (409, "SEMANTIC_INDEX_CONFLICT"),
    SemanticIndexConfirmationRequired: (403, "SEMANTIC_INDEX_CONFIRMATION_REQUIRED"),
    SemanticIndexNothingToDo: (409, "SEMANTIC_INDEX_UP_TO_DATE"),
}


def _invoke[T](response: Response, action: Callable[[], T]) -> T:
    response.headers["Cache-Control"] = "no-store"
    try:
        return action()
    except (ProjectNotFound, InvalidDomainIdentifier):
        raise AppError(
            code="PROJECT_NOT_FOUND", message="Project not found.", status_code=404
        ) from None
    except DomainError as error:
        if type(error) in _ERRORS:
            status, code = _ERRORS[type(error)]
            raise AppError(code=code, message=error.message, status_code=status) from None
        raise map_error(error) from None


Service = Annotated[SemanticIndexService, Depends(get_semantic_index_service)]
Json = Annotated[None, Depends(require_json)]


def create_semantic_index_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(
        prefix=api_prefix + "/projects/{project_id}/semantic-index", tags=["Semantic Index"]
    )

    @router.get("", response_model=IndexStatus)
    def status(project_id: str, response: Response, service: Service) -> IndexStatus:
        return _invoke(response, lambda: service.status(project_id))

    @router.put("/settings", response_model=SettingsView)
    def save_settings(
        project_id: str, payload: SettingsInput, response: Response, service: Service, _json: Json
    ) -> SettingsView:
        return _invoke(
            response,
            lambda: service.save_settings(
                project_id, payload.expected_version, payload.enabled, payload.profile_id
            ),
        )

    @router.post("/build", response_model=BuildResult)
    def build(
        project_id: str, payload: BuildInput, response: Response, service: Service, _json: Json
    ) -> BuildResult:
        return _invoke(
            response,
            lambda: service.build(
                project_id,
                payload.plan_version,
                confirmed=payload.confirm_estimate,
                cloud_consent=payload.cloud_consent,
            ),
        )

    return router
