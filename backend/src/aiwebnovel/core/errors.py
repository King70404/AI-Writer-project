"""Unified API errors and FastAPI exception handlers."""

import json
import re
import secrets
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from aiwebnovel.core.logging import (
    bind_request_id,
    get_logger,
    get_request_id,
    reset_request_id,
)

logger = get_logger("errors")

_SAFE_VALIDATION_TYPE = re.compile(r"\A[a-zA-Z0-9_.-]+\Z")


class AppError(Exception):
    """An expected application error with a stable public representation."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: Mapping[str, Any] | None = None,
        retryable: bool = False,
        suggested_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = dict(details or {})
        self.retryable = retryable
        self.suggested_action = suggested_action


def _request_id_for(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None) or get_request_id()
    if not request_id:
        request_id = f"req_{secrets.token_urlsafe(18)}"
        request.state.request_id = request_id
    return request_id


def _safe_details(details: Mapping[str, Any]) -> dict[str, Any]:
    try:
        serialized = json.dumps(details, ensure_ascii=False, allow_nan=False)
        decoded = json.loads(serialized)
    except (TypeError, ValueError, OverflowError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    details: Mapping[str, Any] | None = None,
    retryable: bool = False,
    suggested_action: str | None = None,
) -> JSONResponse:
    request_id = _request_id_for(request)
    return JSONResponse(
        status_code=status_code,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "code": code,
                "message": message,
                "details": _safe_details(details or {}),
                "retryable": retryable,
                "suggested_action": suggested_action,
            },
            "request_id": request_id,
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert an expected application failure to the frozen error schema."""
    return _error_response(
        request,
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        retryable=exc.retryable,
        suggested_action=exc.suggested_action,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a controlled subset of request validation diagnostics."""
    errors: list[dict[str, str]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        field = ".".join(
            str(part) if isinstance(part, (str, int)) else "field" for part in location
        )
        candidate_type = error.get("type")
        error_type = (
            candidate_type
            if isinstance(candidate_type, str) and _SAFE_VALIDATION_TYPE.fullmatch(candidate_type)
            else "validation_error"
        )
        errors.append(
            {
                "field": field or "request",
                "type": error_type,
                "message": "Invalid request value.",
            }
        )
    return _error_response(
        request,
        code="REQUEST_VALIDATION_ERROR",
        message="请求参数验证失败。",
        status_code=422,
        details={"errors": errors},
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normalize routing and other framework HTTP errors."""
    if exc.status_code == 404:
        return _error_response(
            request,
            code="NOT_FOUND",
            message="请求的资源不存在。",
            status_code=404,
        )
    return _error_response(
        request,
        code="HTTP_ERROR",
        message="请求未能完成。",
        status_code=exc.status_code,
    )


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log diagnostics server-side and expose only a generic 500 response."""
    request_id = _request_id_for(request)
    token = None
    if get_request_id() != request_id:
        token = bind_request_id(request_id)
    try:
        logger.error(
            "Unhandled request exception",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    finally:
        if token is not None:
            reset_request_id(token)

    return _error_response(
        request,
        code="INTERNAL_ERROR",
        message="服务器内部错误。",
        status_code=500,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all handlers used by production and test application instances."""
    app.exception_handler(AppError)(app_error_handler)
    app.exception_handler(RequestValidationError)(validation_error_handler)
    app.exception_handler(StarletteHTTPException)(http_error_handler)
    app.exception_handler(Exception)(internal_error_handler)
