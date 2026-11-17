"""Memory workspace operations use the shared session, CSRF and JSON boundary."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from aiwebnovel.ai_writing.web import map_error, require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.story_memory.models import (
    Fact,
    FactInput,
    MemoryConflict,
    MemoryConsentRequired,
    MemoryInvalid,
    MemoryNotFound,
    PrepareReview,
    Review,
    SendReview,
    Workspace,
)
from aiwebnovel.story_memory.service import StoryMemoryService
from aiwebnovel.usage.budget import SendEstimate
from aiwebnovel.usage.budget_service import UsageBudgetService
from aiwebnovel.usage.budget_web import get_budget_service


def get_memory_service(request: Request) -> StoryMemoryService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            message="Explicit backup and upgrade required.",
            status_code=503,
        )
    service = getattr(request.app.state, "story_memory_service", None)
    if not isinstance(service, StoryMemoryService):
        raise AppError(
            code="MEMORY_UNAVAILABLE", message="Story memory is unavailable.", status_code=503
        )
    return service


def _invoke[T](response: Response, action: Callable[[], T]) -> T:
    response.headers["Cache-Control"] = "no-store"
    try:
        return action()
    except ProjectNotFound:
        raise AppError(
            code="PROJECT_NOT_FOUND", message="Project not found.", status_code=404
        ) from None
    except (MemoryConflict, MemoryInvalid, MemoryNotFound, MemoryConsentRequired) as error:
        status, code = {
            MemoryConflict: (409, "MEMORY_CONFLICT"),
            MemoryInvalid: (422, "MEMORY_INVALID"),
            MemoryNotFound: (404, "MEMORY_NOT_FOUND"),
            MemoryConsentRequired: (403, "MEMORY_CONSENT_REQUIRED"),
        }[type(error)]
        raise AppError(code=code, message=error.message, status_code=status) from None
    except DomainError as error:
        raise map_error(error) from None


Service = Annotated[StoryMemoryService, Depends(get_memory_service)]
Json = Annotated[None, Depends(require_json)]


def create_story_memory_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix + "/chapters/{chapter_id}/memory", tags=["Story Memory"])

    @router.get("/reviews/{review_id}/estimate", response_model=SendEstimate)
    def review_estimate(
        chapter_id: str,
        review_id: str,
        response: Response,
        service: Service,
        budgets: Annotated[UsageBudgetService, Depends(get_budget_service)],
    ) -> SendEstimate:
        def estimate() -> SendEstimate:
            review = service.review_for_estimate(chapter_id, review_id)
            return budgets.estimate(
                project_id=review.project_id,
                chapter_id=review.chapter_id,
                task_id=review.id,
                profile_id=str(review.model["id"]),
                messages=service.messages(review),
            )

        return _invoke(response, estimate)

    @router.get("", response_model=Workspace)
    def workspace(chapter_id: str, response: Response, service: Service) -> Workspace:
        return _invoke(response, lambda: service.workspace(chapter_id))

    @router.post("/facts", response_model=Fact, status_code=201)
    def create_fact(
        chapter_id: str, payload: FactInput, response: Response, service: Service, _json: Json
    ) -> Fact:
        return _invoke(response, lambda: service.save_fact(chapter_id, payload))

    @router.put("/facts/{fact_id}", response_model=Fact)
    def update_fact(
        chapter_id: str,
        fact_id: str,
        payload: FactInput,
        response: Response,
        service: Service,
        _json: Json,
    ) -> Fact:
        return _invoke(response, lambda: service.save_fact(chapter_id, payload, fact_id))

    @router.post("/reviews", response_model=Review, status_code=201)
    def prepare(
        chapter_id: str, payload: PrepareReview, response: Response, service: Service, _json: Json
    ) -> Review:
        return _invoke(
            response,
            lambda: service.prepare(chapter_id, payload.source_revision, payload.profile_id),
        )

    @router.post("/reviews/{review_id}/send", response_model=Review)
    def send(
        chapter_id: str,
        review_id: str,
        payload: SendReview,
        response: Response,
        service: Service,
        _json: Json,
    ) -> Review:
        return _invoke(
            response,
            lambda: service.send(
                chapter_id, review_id, payload.expected_version, payload.cloud_consent
            ),
        )

    return router
