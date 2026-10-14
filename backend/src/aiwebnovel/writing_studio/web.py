"""Protected author actions for reference study and versioned writing methods."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.ai_writing.web import map_error, require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError, InvalidDomainIdentifier
from aiwebnovel.model_gateway.errors import (
    InvalidModelProfile,
    ModelConfigurationUnavailable,
    ModelCredentialUnavailable,
    ModelProfileNotFound,
)
from aiwebnovel.model_gateway.web import map_model_error
from aiwebnovel.writing_studio.application.models import (
    WritingConflict,
    WritingConsentRequired,
    WritingInputInvalid,
    WritingNotFound,
    WritingOutputInvalid,
    WritingReference,
    WritingRule,
    WritingRuleVersion,
)
from aiwebnovel.writing_studio.application.service import WritingStudioService


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CreateReferenceRequest(StrictRequest):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=8000)
    granularity: Literal["sentence", "paragraph"] = "sentence"
    profile_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class AnalyzeRequest(StrictRequest):
    expected_version: int = Field(ge=1)
    cloud_consent: bool = False


class RuleRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=1000)
    applies_to: str = Field(min_length=1, max_length=200)


class CreateRulesRequest(StrictRequest):
    title: str = Field(min_length=1, max_length=120)
    reference_id: str | None = Field(default=None, max_length=36)
    rules: list[RuleRequest] = Field(min_length=1, max_length=8)
    confirmed: bool


class ReviseRulesRequest(CreateRulesRequest):
    expected_version: int = Field(ge=1)


def get_writing_studio(request: Request) -> WritingStudioService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            status_code=503,
            message="Back up and explicitly upgrade the database to use writing study.",
        )
    service = getattr(request.app.state, "writing_studio_service", None)
    if not isinstance(service, WritingStudioService):
        raise AppError(
            code="WRITING_STUDIO_UNAVAILABLE",
            status_code=503,
            message="Writing study is unavailable.",
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
        errors = {
            WritingInputInvalid: ("WRITING_INPUT_INVALID", 422),
            WritingNotFound: ("WRITING_NOT_FOUND", 404),
            WritingConflict: ("WRITING_CONFLICT", 409),
            WritingOutputInvalid: ("WRITING_OUTPUT_INVALID", 502),
            WritingConsentRequired: ("WRITING_CONSENT_REQUIRED", 422),
            InvalidDomainIdentifier: ("WRITING_INPUT_INVALID", 422),
        }
        if type(error) in errors:
            code, status = errors[type(error)]
            raise AppError(code=code, status_code=status, message=error.message) from None
        raise map_error(error) from None


Service = Annotated[WritingStudioService, Depends(get_writing_studio)]
Json = Annotated[None, Depends(require_json)]


def create_writing_studio_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix + "/projects/{project_id}/writing", tags=["Writing Study"])

    @router.get("/references", response_model=tuple[WritingReference, ...])
    def list_references(
        project_id: str, response: Response, service: Service
    ) -> tuple[WritingReference, ...]:
        return _invoke(response, lambda: service.list_references(project_id))

    @router.post("/references", response_model=WritingReference, status_code=201)
    def create_reference(
        project_id: str,
        payload: CreateReferenceRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WritingReference:
        return _invoke(
            response, lambda: service.create_reference(project_id, **payload.model_dump())
        )

    @router.get("/references/{reference_id}", response_model=WritingReference)
    def get_reference(
        project_id: str, reference_id: str, response: Response, service: Service
    ) -> WritingReference:
        return _invoke(response, lambda: service.get_reference(project_id, reference_id))

    @router.post("/references/{reference_id}/analyze", response_model=WritingReference)
    def analyze(
        project_id: str,
        reference_id: str,
        payload: AnalyzeRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WritingReference:
        return _invoke(
            response, lambda: service.analyze(project_id, reference_id, **payload.model_dump())
        )

    @router.get("/rules", response_model=tuple[WritingRuleVersion, ...])
    def list_rules(
        project_id: str, response: Response, service: Service
    ) -> tuple[WritingRuleVersion, ...]:
        return _invoke(response, lambda: service.list_rules(project_id))

    @router.post("/rules", response_model=WritingRuleVersion, status_code=201)
    def create_rules(
        project_id: str,
        payload: CreateRulesRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WritingRuleVersion:
        return _invoke(
            response,
            lambda: service.save_rules(
                project_id,
                title=payload.title,
                reference_id=payload.reference_id,
                rules=tuple(WritingRule(**rule.model_dump()) for rule in payload.rules),
                confirmed=payload.confirmed,
            ),
        )

    @router.post("/rules/{rule_id}/versions", response_model=WritingRuleVersion, status_code=201)
    def revise_rules(
        project_id: str,
        rule_id: str,
        payload: ReviseRulesRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WritingRuleVersion:
        return _invoke(
            response,
            lambda: service.save_rules(
                project_id,
                title=payload.title,
                reference_id=payload.reference_id,
                rules=tuple(WritingRule(**rule.model_dump()) for rule in payload.rules),
                confirmed=payload.confirmed,
                rule_id=rule_id,
                expected_version=payload.expected_version,
            ),
        )

    return router
