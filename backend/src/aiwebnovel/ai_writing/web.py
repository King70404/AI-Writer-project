"""Two candidate-only HTTP operations; no prompts, transport, or ORM access."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.ai_writing.application.models import GenerationCandidate
from aiwebnovel.ai_writing.application.services import AIWritingService
from aiwebnovel.ai_writing.errors import (
    AIContextChanged,
    AIProviderAccessDenied,
    AIProviderAuthFailed,
    AIProviderConfigurationInvalid,
    AIProviderEndpointInvalid,
    AIProviderInvalidResponse,
    AIProviderNotConfigured,
    AIProviderPaymentRequired,
    AIProviderRateLimited,
    AIProviderRequestRejected,
    AIProviderTimeout,
    AIProviderUnavailable,
    InvalidAIInput,
)
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError, InvalidDomainIdentifier
from aiwebnovel.novel_structure.errors import ChapterNotFound
from aiwebnovel.security.request_limits import is_json_media_type
from aiwebnovel.usage.budget import BudgetRefused
from aiwebnovel.usage.models import UsageLedgerUnavailable


class ContinueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    instruction: str = Field(default="", max_length=4000)


class RewriteRequest(ContinueRequest):
    text: str = Field(min_length=1, max_length=50_000)


class ContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    included_sources: tuple[str, ...]
    omitted_sources: tuple[str, ...]
    truncated: bool
    character_count: int


class CandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: str
    text: str
    model: str
    context: ContextResponse


def get_ai_writing_service(request: Request) -> AIWritingService:
    service = getattr(request.app.state, "ai_writing_service", None)
    if not isinstance(service, AIWritingService):
        raise AppError(
            code="AI_SERVICE_UNAVAILABLE",
            message="AI writing service is unavailable.",
            status_code=503,
        )
    return service


def require_json(request: Request) -> None:
    values = request.headers.getlist("Content-Type")
    if len(values) == 1:
        try:
            encoded = values[0].encode("ascii")
        except UnicodeEncodeError:
            encoded = b""
        parameters = [part.strip().lower() for part in values[0].split(";")[1:]]
        if is_json_media_type(encoded) and all(p == "charset=utf-8" for p in parameters):
            return
    raise AppError(
        code="UNSUPPORTED_MEDIA_TYPE",
        message="API request bodies must use UTF-8 JSON.",
        status_code=415,
    )


def map_error(error: DomainError) -> AppError:
    statuses: dict[type[DomainError], tuple[int, str, str]] = {
        AIProviderNotConfigured: (
            503,
            "AI_PROVIDER_NOT_CONFIGURED",
            AIProviderNotConfigured.message,
        ),
        AIProviderConfigurationInvalid: (
            503,
            "AI_PROVIDER_CONFIG_INVALID",
            AIProviderConfigurationInvalid.message,
        ),
        AIProviderUnavailable: (502, "AI_PROVIDER_UNAVAILABLE", AIProviderUnavailable.message),
        AIProviderAuthFailed: (502, "AI_PROVIDER_AUTH_FAILED", AIProviderAuthFailed.message),
        AIProviderAccessDenied: (502, "AI_PROVIDER_ACCESS_DENIED", AIProviderAccessDenied.message),
        AIProviderPaymentRequired: (
            502,
            "AI_PROVIDER_PAYMENT_REQUIRED",
            AIProviderPaymentRequired.message,
        ),
        AIProviderRateLimited: (502, "AI_PROVIDER_RATE_LIMITED", AIProviderRateLimited.message),
        AIProviderEndpointInvalid: (
            502,
            "AI_PROVIDER_ENDPOINT_INVALID",
            AIProviderEndpointInvalid.message,
        ),
        AIProviderRequestRejected: (
            502,
            "AI_PROVIDER_REQUEST_REJECTED",
            AIProviderRequestRejected.message,
        ),
        AIProviderInvalidResponse: (
            502,
            "AI_PROVIDER_INVALID_RESPONSE",
            AIProviderInvalidResponse.message,
        ),
        AIProviderTimeout: (504, "AI_PROVIDER_TIMEOUT", AIProviderTimeout.message),
        InvalidAIInput: (422, "INVALID_AI_INPUT", InvalidAIInput.message),
        AIContextChanged: (409, "AI_CONTEXT_CHANGED", AIContextChanged.message),
        InvalidDomainIdentifier: (422, "INVALID_CHAPTER_ID", "The Chapter identifier is invalid."),
        ChapterNotFound: (404, "CHAPTER_NOT_FOUND", "The Chapter was not found."),
        UsageLedgerUnavailable: (
            503,
            "AI_USAGE_LEDGER_UNAVAILABLE",
            UsageLedgerUnavailable.message,
        ),
        BudgetRefused: (409, "AI_BUDGET_REFUSED", BudgetRefused.message),
    }
    status, code, message = statuses.get(
        type(error), (503, "AI_CONTEXT_UNAVAILABLE", "AI writing context is unavailable.")
    )
    return AppError(code=code, message=message, status_code=status)


def candidate_response(candidate: GenerationCandidate, response: Response) -> CandidateResponse:
    response.headers["Cache-Control"] = "no-store"
    return CandidateResponse(
        operation=candidate.operation,
        text=candidate.text,
        model=candidate.model,
        context=ContextResponse(
            included_sources=candidate.context.included_sources,
            omitted_sources=candidate.context.omitted_sources,
            truncated=candidate.context.truncated,
            character_count=candidate.context.character_count,
        ),
    )


def create_ai_writing_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["AI Writing"])

    @router.post("/chapters/{chapter_id}/ai/continue", response_model=CandidateResponse)
    def continue_chapter(
        chapter_id: str,
        payload: ContinueRequest,
        response: Response,
        service: Annotated[AIWritingService, Depends(get_ai_writing_service)],
        _json: Annotated[None, Depends(require_json)],
    ) -> CandidateResponse:
        try:
            candidate = service.continue_chapter(chapter_id, payload.instruction)
        except DomainError as error:
            raise map_error(error) from None
        return candidate_response(candidate, response)

    @router.post("/chapters/{chapter_id}/ai/rewrite", response_model=CandidateResponse)
    def rewrite_chapter(
        chapter_id: str,
        payload: RewriteRequest,
        response: Response,
        service: Annotated[AIWritingService, Depends(get_ai_writing_service)],
        _json: Annotated[None, Depends(require_json)],
    ) -> CandidateResponse:
        try:
            candidate = service.rewrite_chapter_text(chapter_id, payload.text, payload.instruction)
        except DomainError as error:
            raise map_error(error) from None
        return candidate_response(candidate, response)

    return router
