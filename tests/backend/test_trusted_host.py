"""Host allow-list and untrusted forwarding-header tests."""

import asyncio
import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from aiwebnovel.security.host import HostValidationMiddleware, parse_host_header

pytestmark = pytest.mark.unit


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(
        HostValidationMiddleware,
        trusted_hosts=("127.0.0.1", "localhost"),
    )
    return app


def test_trusted_hosts_accept_exact_hosts_and_valid_ports() -> None:
    with TestClient(_app()) as client:
        for host in ("127.0.0.1", "127.0.0.1:8000", "localhost", "LOCALHOST:65535"):
            response = client.get("/api/v1/health/live", headers={"Host": host})
            assert response.status_code == 200


def test_malicious_hosts_are_rejected_without_reflection() -> None:
    with TestClient(_app()) as client:
        for host in (
            "evil.example",
            "127.0.0.1.evil.example",
            "user@127.0.0.1",
            "127.0.0.1:0",
            "127.0.0.1:65536",
            "127.0.0.1:notaport",
        ):
            response = client.get(
                "/api/v1/health/live",
                headers={"Host": host, "X-Request-ID": "host-check"},
            )
            assert response.status_code == 400
            payload = response.json()
            assert payload["error"]["code"] == "INVALID_HOST"
            assert payload["request_id"] == "host-check"
            assert response.headers["X-Request-ID"] == "host-check"
            assert host not in response.text


def test_forwarded_headers_never_change_actual_host_decision() -> None:
    forged = {
        "X-Forwarded-Host": "127.0.0.1",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-For": "127.0.0.1",
        "Forwarded": "for=127.0.0.1;host=127.0.0.1;proto=https",
    }
    with TestClient(_app()) as client:
        rejected = client.get("/api/v1/health/live", headers={"Host": "evil.example", **forged})
        accepted = client.get(
            "/api/v1/health/live",
            headers={"Host": "127.0.0.1", **{key: "evil.example" for key in forged}},
        )
    assert rejected.status_code == 400
    assert accepted.status_code == 200


def test_parser_rejects_empty_duplicate_and_control_character_hosts() -> None:
    for value in (b"", b"127.0.0.1\x00", b" 127.0.0.1", b"127.0.0.1,evil"):
        with pytest.raises(ValueError):
            parse_host_header(value)

    duplicate = _invoke_raw_host(((b"host", b"127.0.0.1"), (b"host", b"localhost")))
    missing = _invoke_raw_host(())
    assert duplicate["status"] == 400
    assert missing["status"] == 400
    assert json.loads(duplicate["body"])["error"]["code"] == "INVALID_HOST"


def _invoke_raw_host(headers: tuple[tuple[bytes, bytes], ...]) -> dict[str, Any]:
    result: dict[str, Any] = {"body": b""}

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = HostValidationMiddleware(
        downstream,
        trusted_hosts=("127.0.0.1", "localhost"),
    )
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
        "state": {},
    }
    requests = iter(({"type": "http.request", "body": b"", "more_body": False},))

    async def receive() -> Message:
        return next(requests)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    asyncio.run(middleware(scope, receive, send))
    return result
