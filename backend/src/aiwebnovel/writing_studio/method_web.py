"""Explicit F08 comparison endpoints; preparation and ratings never call a model."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.ai_writing.web import require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.usage.budget import SendEstimate
from aiwebnovel.writing_studio.application.method_service import MethodService
from aiwebnovel.writing_studio.application.methods import MethodTemplate, Score
from aiwebnovel.writing_studio.application.models import WritingRuleVersion
from aiwebnovel.writing_studio.web import _invoke, get_writing_studio


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Prepare(StrictRequest):
    chapter_id: str = Field(min_length=1, max_length=60)
    manuscript_revision_id: str = Field(min_length=1, max_length=60)
    plan_revision_id: str = Field(min_length=1, max_length=60)
    rule_version_id: str = Field(min_length=1, max_length=60)
    rule_index: int = Field(ge=0, le=7)
    scene_id: str = Field(min_length=1, max_length=60)
    profile_id: str = Field(min_length=1, max_length=100)


class Send(StrictRequest):
    slot: Literal["A", "B"]
    expected_version: int = Field(ge=1)
    cloud_consent: bool = False


class ScoreRequest(StrictRequest):
    focus: int = Field(ge=1, le=5)
    continuity: int = Field(ge=1, le=5)
    subtext: int = Field(ge=1, le=5)
    persistence: int = Field(ge=1, le=5)
    originality: int = Field(ge=1, le=5)
    reason: str = Field(max_length=500)


class Rate(StrictRequest):
    expected_version: int = Field(ge=1)
    a: ScoreRequest
    b: ScoreRequest


class AnnotationRequest(StrictRequest):
    chapter_id: str = Field(min_length=1, max_length=60)
    manuscript_revision_id: str = Field(min_length=1, max_length=60)
    rule_version_id: str = Field(min_length=1, max_length=60)
    rule_index: int = Field(ge=0, le=7)
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    judgment: Literal["embodied", "not_embodied", "not_applicable"]
    reason: str = Field(min_length=1, max_length=500)


class TemplateRequest(StrictRequest):
    source_rule_version_id: str = Field(min_length=1, max_length=60)
    source_rule_index: int = Field(ge=0, le=7)
    name: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=1000)
    applies_to: str = Field(min_length=1, max_length=200)
    excludes: str = Field(default="", max_length=200)
    scene_tags: list[str] = Field(default_factory=list, max_length=8)
    priority: int = Field(default=3, ge=1, le=5)
    confirmed: bool


class Confirm(StrictRequest):
    confirmed: bool


def get_method_service(request: Request) -> MethodService:
    service = get_writing_studio(request).method_service
    if not isinstance(service, MethodService):
        raise AppError(
            code="METHOD_VALIDATION_UNAVAILABLE",
            status_code=503,
            message="Method validation is unavailable.",
        )
    return service


Service = Annotated[MethodService, Depends(get_method_service)]
Json = Annotated[None, Depends(require_json)]


def create_method_router(*, api_prefix: str) -> APIRouter:
    root = APIRouter()
    router = APIRouter(
        prefix=api_prefix + "/projects/{project_id}/writing/method-trials", tags=["Writing Methods"]
    )

    @router.post("", status_code=201)
    def prepare(
        project_id: str, payload: Prepare, response: Response, service: Service, _json: Json
    ) -> dict[str, object]:
        values = payload.model_dump()
        chapter_id = values.pop("chapter_id")
        return _invoke(response, lambda: service.prepare(project_id, chapter_id, **values))

    @router.get("")
    def list_trials(
        project_id: str, chapter_id: str, response: Response, service: Service
    ) -> list[dict[str, object]]:
        return _invoke(response, lambda: service.list(project_id, chapter_id))

    @router.get("/{trial_id}")
    def get(
        project_id: str, trial_id: str, response: Response, service: Service
    ) -> dict[str, object]:
        return _invoke(response, lambda: service.get(project_id, trial_id))

    @router.get("/{trial_id}/estimate/{slot}", response_model=SendEstimate)
    def estimate(
        project_id: str,
        trial_id: str,
        slot: Literal["A", "B"],
        response: Response,
        service: Service,
    ) -> SendEstimate:
        return _invoke(response, lambda: service.estimate(project_id, trial_id, slot))

    @router.post("/{trial_id}/send")
    def send(
        project_id: str,
        trial_id: str,
        payload: Send,
        response: Response,
        service: Service,
        _json: Json,
    ) -> dict[str, object]:
        return _invoke(response, lambda: service.send(project_id, trial_id, **payload.model_dump()))

    @router.post("/{trial_id}/rate")
    def rate(
        project_id: str,
        trial_id: str,
        payload: Rate,
        response: Response,
        service: Service,
        _json: Json,
    ) -> dict[str, object]:
        return _invoke(
            response,
            lambda: service.rate(
                project_id,
                trial_id,
                expected_version=payload.expected_version,
                a=Score(**payload.a.model_dump()),
                b=Score(**payload.b.model_dump()),
            ),
        )

    auxiliary = APIRouter(
        prefix=api_prefix + "/projects/{project_id}/writing", tags=["Writing Methods"]
    )

    @auxiliary.post("/method-annotations", status_code=201)
    def annotate(
        project_id: str,
        payload: AnnotationRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> dict[str, str]:
        values = payload.model_dump()
        chapter_id = values.pop("chapter_id")
        return _invoke(response, lambda: {"id": service.annotate(project_id, chapter_id, **values)})

    @auxiliary.get("/method-annotations/{chapter_id}")
    def annotations(
        project_id: str, chapter_id: str, response: Response, service: Service
    ) -> tuple[dict[str, object], ...]:
        return _invoke(response, lambda: service.annotations(project_id, chapter_id))

    @auxiliary.post("/method-templates", response_model=MethodTemplate, status_code=201)
    def create_template(
        project_id: str, payload: TemplateRequest, response: Response, service: Service, _json: Json
    ) -> MethodTemplate:
        values = payload.model_dump()
        values["scene_tags"] = tuple(payload.scene_tags)
        return _invoke(response, lambda: service.create_template(project_id, **values))

    @auxiliary.get("/method-templates", response_model=tuple[MethodTemplate, ...])
    def templates(
        project_id: str, response: Response, service: Service
    ) -> tuple[MethodTemplate, ...]:
        return _invoke(response, lambda: service.templates(project_id))

    @auxiliary.delete("/method-templates/{template_id}", status_code=204)
    def delete_template(
        project_id: str, template_id: str, response: Response, service: Service, _json: Json
    ) -> None:
        return _invoke(response, lambda: service.delete_template(project_id, template_id))

    @auxiliary.post(
        "/method-templates/{template_id}/copy", response_model=WritingRuleVersion, status_code=201
    )
    def copy_template(
        project_id: str,
        template_id: str,
        payload: Confirm,
        response: Response,
        service: Service,
        _json: Json,
    ) -> WritingRuleVersion:
        return _invoke(
            response,
            lambda: service.copy_template(project_id, template_id, confirmed=payload.confirmed),
        )

    root.include_router(router)
    root.include_router(auxiliary)
    return root
