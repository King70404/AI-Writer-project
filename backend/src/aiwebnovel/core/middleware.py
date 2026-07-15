"""Request-scoped middleware for correlation and safe access logging."""

import re
import secrets
from collections.abc import Callable
from time import perf_counter

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from aiwebnovel.core.logging import (
    bind_request_id,
    get_logger,
    reset_request_id,
)

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
logger = get_logger("middleware")


def is_valid_request_id(value: str | None) -> bool:
    """Return whether a client request ID is safe to echo and log."""
    if value is None or not value or len(value) > MAX_REQUEST_ID_LENGTH:
        return False
    return _SAFE_REQUEST_ID.fullmatch(value) is not None


def generate_request_id() -> str:
    """Generate a non-predictable, log-safe request identifier."""
    return f"req_{secrets.token_urlsafe(18)}"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Validate or generate a request ID and scope it to one request."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        path_sanitizer: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(app)
        self._path_sanitizer = path_sanitizer or (lambda path: path)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied_request_id = request.headers.get(REQUEST_ID_HEADER)
        if supplied_request_id is not None and is_valid_request_id(supplied_request_id):
            request_id = supplied_request_id
        else:
            request_id = generate_request_id()
        request.state.request_id = request_id
        token = bind_request_id(request_id)
        started_at = perf_counter()

        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            elapsed_ms = (perf_counter() - started_at) * 1000
            try:
                safe_path = self._path_sanitizer(request.url.path)
            except Exception:  # noqa: BLE001 - diagnostic helpers must never break a request.
                safe_path = "/"
            logger.info(
                "request completed method=%s path=%s status=%s duration_ms=%.3f",
                request.method,
                safe_path,
                response.status_code,
                elapsed_ms,
            )
            return response
        finally:
            reset_request_id(token)
