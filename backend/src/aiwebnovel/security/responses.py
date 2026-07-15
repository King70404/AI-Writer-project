"""Small ASGI response helpers for failures raised before FastAPI routing."""

from __future__ import annotations

import json
from typing import Any

from starlette.types import Message, Scope, Send

from aiwebnovel.core.middleware import generate_request_id, is_valid_request_id


def request_id_for_scope(scope: Scope) -> str:
    """Return one safe request ID and bind it to the ASGI scope state."""
    state = scope.setdefault("state", {})
    existing = state.get("request_id")
    if isinstance(existing, str) and is_valid_request_id(existing):
        return existing

    supplied: str | None = None
    for name, value in scope.get("headers", ()):
        if name.lower() == b"x-request-id":
            try:
                candidate = value.decode("ascii")
            except UnicodeDecodeError:
                break
            if supplied is not None:
                break
            supplied = candidate
    request_id = (
        supplied
        if supplied is not None and is_valid_request_id(supplied)
        else generate_request_id()
    )
    state["request_id"] = request_id
    return request_id


async def send_security_error(
    scope: Scope,
    send: Send,
    *,
    status_code: int,
    code: str,
    message: str,
) -> None:
    """Send the project's stable, path-free JSON error representation."""
    request_id = request_id_for_scope(scope)
    content: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": {},
            "retryable": False,
            "suggested_action": None,
        },
        "request_id": request_id,
    }
    body = json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"cache-control", b"no-store"),
        (b"x-request-id", request_id.encode("ascii")),
    ]
    start: Message = {
        "type": "http.response.start",
        "status": status_code,
        "headers": headers,
    }
    await send(start)
    await send({"type": "http.response.body", "body": body})
