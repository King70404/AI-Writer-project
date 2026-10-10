"""Explicit author confirmation for backed-up AI database activation."""

from collections.abc import Callable
from threading import Lock
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from aiwebnovel.ai_writing.web import require_json
from aiwebnovel.core.errors import AppError


class AIWorkflowSetupService:
    def __init__(self, activate: Callable[[], None]) -> None:
        self._activate = activate
        self._lock = Lock()

    def enable(self) -> None:
        if not self._lock.acquire(blocking=False):
            raise AppError(
                code="AI_WORKFLOW_UPGRADE_BUSY",
                message="AI setup is already running. Wait before retrying.",
                status_code=409,
            )
        try:
            self._activate()
        finally:
            self._lock.release()


class UpgradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    confirm_backup: bool


class UpgradeResponse(BaseModel):
    status: Literal["ready"] = "ready"


def create_ai_setup_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix + "/ai/workflow-setup", tags=["AI Setup"])

    @router.post("/upgrade", response_model=UpgradeResponse)
    def enable(
        payload: UpgradeRequest,
        request: Request,
        response: Response,
        _json: Annotated[None, Depends(require_json)],
    ) -> UpgradeResponse:
        response.headers["Cache-Control"] = "no-store"
        if not payload.confirm_backup:
            raise AppError(
                code="AI_WORKFLOW_UPGRADE_CONFIRMATION_REQUIRED",
                message="Confirm the database backup and upgrade first.",
                status_code=422,
            )
        service = getattr(request.app.state, "ai_workflow_setup_service", None)
        if not isinstance(service, AIWorkflowSetupService):
            raise AppError(
                code="AI_WORKFLOW_UPGRADE_FAILED",
                message="AI setup is unavailable; manual writing remains available.",
                status_code=503,
            )
        service.enable()
        return UpgradeResponse()

    return router
