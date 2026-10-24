"""Author-entered model prices and novel budgets; reading or saving never calls a model."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.ai_writing.web import require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError, InvalidDomainIdentifier
from aiwebnovel.model_gateway.errors import (
    InvalidModelProfile,
    ModelConfigurationUnavailable,
    ModelCredentialUnavailable,
    ModelProfileNotFound,
)
from aiwebnovel.model_gateway.web import map_model_error
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.usage.budget import (
    BudgetInputInvalid,
    BudgetVersionConflict,
    BudgetView,
    PriceState,
)
from aiwebnovel.usage.budget_service import UsageBudgetService


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PutPriceRequest(_Body):
    expected_version: int = Field(ge=0, le=1_000_000)
    currency: str = Field(min_length=3, max_length=3)
    input_per_million: str = Field(min_length=1, max_length=20)
    output_per_million: str = Field(min_length=1, max_length=20)


class PutBudgetRequest(_Body):
    expected_version: int = Field(ge=0, le=1_000_000)
    mode: Literal["off", "warn", "strict"]
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    task_limit: str | None = Field(default=None, min_length=1, max_length=20)
    monthly_limit: str | None = Field(default=None, min_length=1, max_length=20)


def get_budget_service(request: Request) -> UsageBudgetService:
    if getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="AI_WORKFLOW_SCHEMA_REQUIRED",
            message="Back up and explicitly upgrade the database to use budgets.",
            status_code=503,
        )
    service = getattr(request.app.state, "usage_budget_service", None)
    if not isinstance(service, UsageBudgetService):
        raise AppError(
            code="USAGE_BUDGET_UNAVAILABLE",
            message="Budgets and prices are unavailable.",
            status_code=503,
        )
    return service


def _invoke[T](response: Response, call: Callable[[], T]) -> T:
    response.headers["Cache-Control"] = "no-store"
    try:
        return call()
    except BudgetInputInvalid:
        raise AppError(
            code="BUDGET_INPUT_INVALID", message=BudgetInputInvalid.message, status_code=422
        ) from None
    except BudgetVersionConflict:
        raise AppError(
            code="BUDGET_VERSION_CONFLICT", message=BudgetVersionConflict.message, status_code=409
        ) from None
    except InvalidDomainIdentifier:
        raise AppError(
            code="INVALID_PROJECT_ID", message="The Project identifier is invalid.", status_code=422
        ) from None
    except ProjectNotFound:
        raise AppError(
            code="PROJECT_NOT_FOUND", message="Project not found.", status_code=404
        ) from None
    except (
        InvalidModelProfile,
        ModelConfigurationUnavailable,
        ModelCredentialUnavailable,
        ModelProfileNotFound,
    ) as error:
        raise map_model_error(error) from None
    except DomainError:
        raise AppError(
            code="USAGE_BUDGET_UNAVAILABLE",
            message="Budgets and prices are unavailable.",
            status_code=503,
        ) from None


Service = Annotated[UsageBudgetService, Depends(get_budget_service)]
Json = Annotated[None, Depends(require_json)]


def create_budget_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix, tags=["Model Budgets"])

    @router.get("/ai/models/{profile_id}/price", response_model=PriceState)
    def get_price(profile_id: str, response: Response, service: Service) -> PriceState:
        return _invoke(response, lambda: service.price_state(profile_id))

    @router.put("/ai/models/{profile_id}/price", response_model=PriceState)
    def put_price(
        profile_id: str,
        payload: PutPriceRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> PriceState:
        return _invoke(response, lambda: service.put_price(profile_id, **payload.model_dump()))

    @router.get("/projects/{project_id}/budget", response_model=BudgetView)
    def get_budget(project_id: str, response: Response, service: Service) -> BudgetView:
        return _invoke(response, lambda: service.budget_view(project_id))

    @router.put("/projects/{project_id}/budget", response_model=BudgetView)
    def put_budget(
        project_id: str,
        payload: PutBudgetRequest,
        response: Response,
        service: Service,
        _json: Json,
    ) -> BudgetView:
        return _invoke(response, lambda: service.put_budget(project_id, **payload.model_dump()))

    return router
