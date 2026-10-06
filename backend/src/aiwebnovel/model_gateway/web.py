"""Model configuration routes protected by the application's session/CSRF middleware."""

from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from aiwebnovel.ai_writing.web import require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.model_gateway.errors import (
    InvalidModelProfile,
    ModelConfigurationUnavailable,
    ModelCredentialUnavailable,
    ModelProfileNotFound,
)
from aiwebnovel.model_gateway.models import MAX_OUTPUT_TOKENS, ModelProfile
from aiwebnovel.model_gateway.service import ModelGatewayService


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["local", "cloud"]
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    max_output_tokens: int = Field(default=2048, ge=1, le=MAX_OUTPUT_TOKENS)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)


class ProfileUpdate(ProfileInput):
    clear_key: bool = False


class ProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    name: str
    kind: Literal["local", "cloud"]
    base_url: str
    model: str
    max_output_tokens: int
    has_key: bool


class ProfilesResponse(BaseModel):
    items: tuple[ProfileResponse, ...]


def get_model_gateway_service(request: Request) -> ModelGatewayService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            message="Back up and explicitly upgrade the database to use AI collaboration.",
            status_code=503,
        )
    service = getattr(request.app.state, "model_gateway_service", None)
    if not isinstance(service, ModelGatewayService):
        raise AppError(
            code="MODEL_GATEWAY_UNAVAILABLE",
            message="Model configuration service is unavailable.",
            status_code=503,
        )
    return service


def map_model_error(error: DomainError) -> AppError:
    statuses = {
        InvalidModelProfile: (422, "INVALID_MODEL_PROFILE"),
        ModelProfileNotFound: (404, "MODEL_PROFILE_NOT_FOUND"),
        ModelCredentialUnavailable: (503, "MODEL_CREDENTIAL_UNAVAILABLE"),
        ModelConfigurationUnavailable: (503, "MODEL_CONFIGURATION_UNAVAILABLE"),
    }
    status, code = statuses.get(type(error), (503, "MODEL_GATEWAY_UNAVAILABLE"))
    return AppError(code=code, message=error.message, status_code=status)


def _response(profile: ModelProfile) -> ProfileResponse:
    return ProfileResponse(**asdict(profile))


def create_model_gateway_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["AI Models"])

    @router.get("/ai/models", response_model=ProfilesResponse)
    def list_profiles(
        response: Response,
        service: Annotated[ModelGatewayService, Depends(get_model_gateway_service)],
    ) -> ProfilesResponse:
        response.headers["Cache-Control"] = "no-store"
        try:
            return ProfilesResponse(
                items=tuple(_response(item) for item in service.list_profiles())
            )
        except DomainError as error:
            raise map_model_error(error) from None

    @router.post("/ai/models", response_model=ProfileResponse, status_code=201)
    def create_profile(
        payload: ProfileInput,
        response: Response,
        service: Annotated[ModelGatewayService, Depends(get_model_gateway_service)],
        _json: Annotated[None, Depends(require_json)],
    ) -> ProfileResponse:
        response.headers["Cache-Control"] = "no-store"
        key = payload.api_key.get_secret_value() if payload.api_key else None
        try:
            return _response(
                service.create_profile(
                    name=payload.name,
                    kind=payload.kind,
                    base_url=payload.base_url,
                    model=payload.model,
                    max_output_tokens=payload.max_output_tokens,
                    api_key=key,
                )
            )
        except DomainError as error:
            raise map_model_error(error) from None

    @router.put("/ai/models/{profile_id}", response_model=ProfileResponse)
    def update_profile(
        profile_id: str,
        payload: ProfileUpdate,
        response: Response,
        service: Annotated[ModelGatewayService, Depends(get_model_gateway_service)],
        _json: Annotated[None, Depends(require_json)],
    ) -> ProfileResponse:
        response.headers["Cache-Control"] = "no-store"
        key = payload.api_key.get_secret_value() if payload.api_key else None
        try:
            return _response(
                service.update_profile(
                    profile_id,
                    name=payload.name,
                    kind=payload.kind,
                    base_url=payload.base_url,
                    model=payload.model,
                    max_output_tokens=payload.max_output_tokens,
                    api_key=key,
                    clear_key=payload.clear_key,
                )
            )
        except DomainError as error:
            raise map_model_error(error) from None

    @router.delete("/ai/models/{profile_id}", status_code=204)
    def remove_profile(
        profile_id: str,
        service: Annotated[ModelGatewayService, Depends(get_model_gateway_service)],
    ) -> Response:
        try:
            service.remove_profile(profile_id)
        except DomainError as error:
            raise map_model_error(error) from None
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    return router
