"""Bounded streaming request-body and structured JSON media-type enforcement."""

from __future__ import annotations

import re
from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aiwebnovel.security.responses import send_security_error

BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_MEDIA_SUBTYPE = re.compile(r"^[!#$%&'*+.^_`|~0-9a-z-]+$")


class RequestLimitConfigurationError(ValueError):
    """Raised when request-boundary configuration cannot be enforced safely."""


def is_json_media_type(value: bytes) -> bool:
    """Return whether one Content-Type value identifies JSON or a +json type."""
    try:
        decoded = value.decode("ascii")
    except UnicodeDecodeError:
        return False
    media_type = decoded.split(";", 1)[0].strip().lower()
    if media_type == "application/json":
        return True
    if not media_type.startswith("application/"):
        return False
    subtype = media_type.removeprefix("application/")
    return (
        len(subtype) > len("+json")
        and subtype.endswith("+json")
        and _MEDIA_SUBTYPE.fullmatch(subtype) is not None
    )


def _header_values(scope: Scope, name: bytes) -> list[bytes]:
    return [value for key, value in scope.get("headers", ()) if key.lower() == name]


def _declared_content_length(scope: Scope) -> int | None:
    values = _header_values(scope, b"content-length")
    if len(values) != 1:
        return None
    try:
        text = values[0].decode("ascii")
    except UnicodeDecodeError:
        return None
    if not text.isdecimal():
        return None
    return int(text)


def _is_api_path(path: str, api_prefix: str) -> bool:
    return path == api_prefix or path.startswith(f"{api_prefix}/")


class RequestLimitsMiddleware:
    """Read body streams only up to a fixed cap before routing structured API requests."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        api_prefix: str = "/api",
        methods: Iterable[str] = BODY_METHODS,
    ) -> None:
        if not isinstance(max_body_bytes, int) or isinstance(max_body_bytes, bool):
            raise RequestLimitConfigurationError("max_body_bytes must be an integer")
        if max_body_bytes <= 0:
            raise RequestLimitConfigurationError("max_body_bytes must be positive")
        if not api_prefix.startswith("/") or api_prefix == "/" or api_prefix.endswith("/"):
            raise RequestLimitConfigurationError("api_prefix must identify a non-root path")
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.api_prefix = api_prefix
        self.methods = frozenset(method.upper() for method in methods)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method", "").upper() not in self.methods
            or not _is_api_path(str(scope.get("path", "")), self.api_prefix)
        ):
            await self.app(scope, receive, send)
            return

        declared_length = _declared_content_length(scope)
        if declared_length is not None and declared_length > self.max_body_bytes:
            await self._too_large(scope, send)
            return

        messages: list[Message] = []
        total = 0
        content_types = _header_values(scope, b"content-type")
        content_type_is_json = len(content_types) == 1 and is_json_media_type(content_types[0])
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            body = message.get("body", b"")
            if body:
                total += len(body)
                if total > self.max_body_bytes:
                    await self._too_large(scope, send)
                    return
                if not content_type_is_json:
                    await send_security_error(
                        scope,
                        send,
                        status_code=415,
                        code="UNSUPPORTED_MEDIA_TYPE",
                        message="API request bodies must use a JSON content type.",
                    )
                    return
            if not message.get("more_body", False):
                break

        pending = iter(messages)

        async def replay_receive() -> Message:
            try:
                return next(pending)
            except StopIteration:
                return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _too_large(scope: Scope, send: Send) -> None:
        await send_security_error(
            scope,
            send,
            status_code=413,
            code="REQUEST_TOO_LARGE",
            message="The request body exceeds the allowed size.",
        )
