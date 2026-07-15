"""Streaming API body-size and JSON content-type boundary tests."""

import asyncio
import json
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from aiwebnovel.security.request_limits import RequestLimitsMiddleware, is_json_media_type

pytestmark = pytest.mark.unit


def _app(limit: int = 8) -> FastAPI:
    app = FastAPI()

    @app.post("/api/test")
    async def api_echo(request: Request) -> dict[str, int]:
        return {"length": len(await request.body())}

    @app.post("/static/test")
    async def static_echo(request: Request) -> dict[str, int]:
        return {"length": len(await request.body())}

    app.add_middleware(RequestLimitsMiddleware, max_body_bytes=limit)
    return app


def test_small_json_variants_and_empty_bodies_pass() -> None:
    with TestClient(_app(limit=64)) as client:
        for media_type in (
            "application/json",
            "application/json; charset=utf-8",
            "application/problem+json",
            "application/vnd.aiwebnovel+json; charset=UTF-8",
        ):
            response = client.post("/api/test", content=b"{}", headers={"Content-Type": media_type})
            assert response.status_code == 200
            assert response.json() == {"length": 2}
        empty = client.post("/api/test", content=b"")
    assert empty.status_code == 200
    assert empty.json() == {"length": 0}


def test_non_json_or_missing_content_type_is_rejected_only_for_nonempty_api_body() -> None:
    body_marker = b"request-body-must-not-be-reflected"
    with TestClient(_app(limit=64)) as client:
        for headers in (
            {"Content-Type": "text/plain"},
            {"Content-Type": "application/x-www-form-urlencoded"},
            {},
        ):
            response = client.post("/api/test", content=body_marker, headers=headers)
            assert response.status_code == 415
            assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
            if body_marker.decode("ascii") in response.text:
                pytest.fail("request body was reflected in a media-type error")


def test_invalid_content_type_stops_after_the_first_nonempty_chunk() -> None:
    result = _invoke(
        path="/api/test",
        headers=((b"host", b"127.0.0.1"), (b"content-type", b"text/plain")),
        messages=(
            {"type": "http.request", "body": b"first", "more_body": True},
            {"type": "http.request", "body": b"must-not-read", "more_body": False},
        ),
        limit=64,
    )

    assert result["status"] == 415
    assert result["receive_count"] == 1
    assert result["downstream_called"] is False


def test_declared_content_length_over_limit_rejects_without_reading_body() -> None:
    result = _invoke(
        path="/api/test",
        headers=((b"host", b"127.0.0.1"), (b"content-length", b"9")),
        messages=(({"type": "http.request", "body": b"never-read", "more_body": False}),),
        limit=8,
        fail_if_receive_called=True,
    )
    assert result["status"] == 413
    assert json.loads(result["body"])["error"]["code"] == "REQUEST_TOO_LARGE"
    assert result["downstream_called"] is False


def test_streaming_without_content_length_stops_on_first_over_limit_chunk() -> None:
    result = _invoke(
        path="/api/test",
        headers=((b"host", b"127.0.0.1"), (b"content-type", b"application/json")),
        messages=(
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"56789", "more_body": True},
            {"type": "http.request", "body": b"must-not-read", "more_body": False},
        ),
        limit=8,
    )
    assert result["status"] == 413
    assert result["receive_count"] == 2
    assert result["downstream_called"] is False


def test_underdeclared_actual_body_is_still_rejected() -> None:
    result = _invoke(
        path="/api/test",
        headers=(
            (b"host", b"127.0.0.1"),
            (b"content-type", b"application/json"),
            (b"content-length", b"1"),
        ),
        messages=(
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"56789", "more_body": False},
        ),
        limit=8,
    )
    assert result["status"] == 413


def test_non_api_body_is_not_read_or_restricted_by_global_api_policy() -> None:
    with TestClient(_app(limit=1)) as client:
        response = client.post(
            "/static/test",
            content=b"plain static content",
            headers={"Content-Type": "text/plain"},
        )
    assert response.status_code == 200
    assert response.json() == {"length": len(b"plain static content")}


def test_json_media_type_parser_rejects_lookalikes_and_non_ascii() -> None:
    assert is_json_media_type(b"application/json") is True
    assert is_json_media_type(b"application/problem+json") is True
    assert is_json_media_type(b"text/json") is False
    assert is_json_media_type(b"application/jsonp") is False
    assert is_json_media_type(b"application/+json") is False
    assert is_json_media_type(b"application/foo/bar+json") is False
    assert is_json_media_type(b"application/\xff+json") is False


def _invoke(
    *,
    path: str,
    headers: tuple[tuple[bytes, bytes], ...],
    messages: tuple[Message, ...],
    limit: int,
    fail_if_receive_called: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "body": b"",
        "downstream_called": False,
        "receive_count": 0,
    }

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        del scope
        result["downstream_called"] = True
        body = b""
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body})

    middleware = RequestLimitsMiddleware(downstream, max_body_bytes=limit)
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
        "state": {},
    }
    pending = iter(messages)

    async def receive() -> Message:
        if fail_if_receive_called:
            raise AssertionError("body receive should not have been called")
        result["receive_count"] += 1
        return next(pending)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    asyncio.run(middleware(scope, receive, send))
    return result
