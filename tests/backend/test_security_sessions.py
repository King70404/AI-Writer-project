"""Process-local session lifecycle, cookie, and capacity tests."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aiwebnovel.security.sessions import (
    InMemorySessionManager,
    SessionStatus,
    create_security_router,
)

pytestmark = pytest.mark.unit


def _token_factory(values: Iterator[str]):
    return lambda: next(values)


def test_session_endpoint_returns_independent_token_and_strict_http_only_cookie() -> None:
    manager = InMemorySessionManager(ttl_seconds=28_800, max_entries=16)
    app = FastAPI()
    app.include_router(create_security_router(manager))

    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        response = client.get("/api/v1/security/session")

    assert response.status_code == 200
    payload = response.json()
    cookie = response.headers["set-cookie"]
    session_id = response.cookies["aiwebnovel_session"]
    assert payload["expires_in_seconds"] == 28_800
    assert payload["csrf_token"] != session_id
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/api" in cookie
    assert "Max-Age=28800" in cookie
    assert "Domain=" not in cookie
    assert "Secure" not in cookie
    assert response.headers["Cache-Control"] == "no-store"
    assert manager.validate_csrf(session_id, payload["csrf_token"]) is SessionStatus.ACTIVE


def test_https_session_cookie_is_secure_without_consulting_forwarded_proto() -> None:
    manager = InMemorySessionManager(ttl_seconds=60, max_entries=2)
    app = FastAPI()
    app.include_router(create_security_router(manager))
    with TestClient(app, base_url="https://127.0.0.1") as client:
        response = client.get(
            "/api/v1/security/session",
            headers={"X-Forwarded-Proto": "http"},
        )
    assert "Secure" in response.headers["set-cookie"]


def test_two_sessions_are_distinct_and_repr_hides_both_secrets() -> None:
    values = iter(("session-one", "csrf-one", "session-two", "csrf-two"))
    manager = InMemorySessionManager(
        ttl_seconds=60,
        max_entries=2,
        token_factory=_token_factory(values),
    )
    first = manager.issue()
    second = manager.issue()
    assert first.session_id != second.session_id
    assert first.csrf_token != second.csrf_token
    assert first.session_id not in repr(first)
    assert first.csrf_token not in repr(first)


def test_expired_session_is_rejected_without_renewal() -> None:
    now = {"value": 100.0}
    manager = InMemorySessionManager(
        ttl_seconds=10,
        max_entries=2,
        clock=lambda: now["value"],
    )
    issued = manager.issue()
    now["value"] = 110.0
    assert manager.status(issued.session_id) is SessionStatus.EXPIRED
    assert manager.status(issued.session_id) is SessionStatus.MISSING
    assert len(manager) == 0


def test_capacity_evicts_oldest_after_expired_cleanup() -> None:
    now = {"value": 1.0}
    values = iter(
        (
            "session-one",
            "csrf-one",
            "session-two",
            "csrf-two",
            "session-three",
            "csrf-three",
        )
    )
    manager = InMemorySessionManager(
        ttl_seconds=10,
        max_entries=2,
        clock=lambda: now["value"],
        token_factory=_token_factory(values),
    )
    first = manager.issue()
    second = manager.issue()
    third = manager.issue()
    assert len(manager) == 2
    assert manager.status(first.session_id) is SessionStatus.MISSING
    assert manager.status(second.session_id) is SessionStatus.ACTIVE
    assert manager.status(third.session_id) is SessionStatus.ACTIVE


def test_new_manager_does_not_share_sessions_with_old_instance() -> None:
    first_manager = InMemorySessionManager(ttl_seconds=60, max_entries=2)
    issued = first_manager.issue()
    restarted_manager = InMemorySessionManager(ttl_seconds=60, max_entries=2)
    assert first_manager.status(issued.session_id) is SessionStatus.ACTIVE
    assert restarted_manager.status(issued.session_id) is SessionStatus.MISSING


def test_clear_invalidates_all_sessions_for_application_shutdown() -> None:
    manager = InMemorySessionManager(ttl_seconds=60, max_entries=2)
    issued = manager.issue()
    assert manager.status(issued.session_id) is SessionStatus.ACTIVE
    manager.clear()
    assert len(manager) == 0
    assert manager.status(issued.session_id) is SessionStatus.MISSING


def test_openapi_describes_session_as_non_authenticating_infrastructure() -> None:
    app = FastAPI()
    app.include_router(
        create_security_router(InMemorySessionManager(ttl_seconds=60, max_entries=2))
    )
    operation = app.openapi()["paths"]["/api/v1/security/session"]["get"]
    assert "not login" in operation["description"]
    serialized_schema = str(app.openapi()).lower()
    assert "password" not in serialized_schema
    assert "authorization" not in serialized_schema
