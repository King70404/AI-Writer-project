"""Origin and CSRF protection tests using only temporary in-test routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aiwebnovel.security.csrf import CSRFMiddleware
from aiwebnovel.security.sessions import InMemorySessionManager

pytestmark = pytest.mark.unit


def _protected_app(manager: InMemorySessionManager) -> FastAPI:
    app = FastAPI()

    @app.post("/api/test/write")
    async def temporary_write() -> dict[str, bool]:
        return {"accepted": True}

    @app.get("/api/test/read")
    async def temporary_read() -> dict[str, bool]:
        return {"accepted": True}

    @app.options("/api/test/write")
    async def temporary_options() -> dict[str, bool]:
        return {"accepted": True}

    app.add_middleware(
        CSRFMiddleware,
        session_manager=manager,
        allowed_origins=("http://127.0.0.1:5173",),
    )
    return app


def _headers(session_id: str, csrf_token: str, *, origin: str | None) -> dict[str, str]:
    headers = {
        "Host": "127.0.0.1:8000",
        "Cookie": f"aiwebnovel_session={session_id}",
        "X-CSRF-Token": csrf_token,
    }
    if origin is not None:
        headers["Origin"] = origin
    return headers


def test_same_origin_cookie_and_matching_csrf_pass() -> None:
    manager = InMemorySessionManager(ttl_seconds=60, max_entries=4)
    issued = manager.issue()
    with TestClient(_protected_app(manager), base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/api/test/write",
            headers=_headers(
                issued.session_id,
                issued.csrf_token,
                origin="http://127.0.0.1:8000",
            ),
        )
    assert response.status_code == 200
    assert response.json() == {"accepted": True}


def test_explicit_development_origin_is_allowed_without_trusting_forwarded_headers() -> None:
    manager = InMemorySessionManager(ttl_seconds=60, max_entries=4)
    issued = manager.issue()
    headers = _headers(
        issued.session_id,
        issued.csrf_token,
        origin="http://127.0.0.1:5173",
    )
    headers.update(
        {
            "X-Forwarded-Host": "evil.example",
            "X-Forwarded-Proto": "https",
            "Forwarded": "host=evil.example;proto=https",
        }
    )
    with TestClient(_protected_app(manager), base_url="http://127.0.0.1:8000") as client:
        response = client.post("/api/test/write", headers=headers)
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("origin", "cookie", "csrf", "expected_code"),
    [
        ("http://127.0.0.1:8000", None, "valid", "SESSION_REQUIRED"),
        ("http://127.0.0.1:8000", "valid", None, "CSRF_TOKEN_REQUIRED"),
        ("http://127.0.0.1:8000", "valid", "wrong", "CSRF_TOKEN_INVALID"),
        ("https://external.example", "valid", "valid", "ORIGIN_NOT_ALLOWED"),
        ("null", "valid", "valid", "ORIGIN_NOT_ALLOWED"),
        (None, "valid", "valid", "ORIGIN_NOT_ALLOWED"),
        ("http://user@127.0.0.1:8000", "valid", "valid", "ORIGIN_NOT_ALLOWED"),
    ],
)
def test_missing_or_invalid_csrf_boundaries_are_rejected_without_secret_reflection(
    origin: str | None,
    cookie: str | None,
    csrf: str | None,
    expected_code: str,
) -> None:
    manager = InMemorySessionManager(ttl_seconds=60, max_entries=4)
    issued = manager.issue()
    headers = {"Host": "127.0.0.1:8000"}
    if origin is not None:
        headers["Origin"] = origin
    if cookie is not None:
        headers["Cookie"] = f"aiwebnovel_session={issued.session_id}"
    if csrf is not None:
        headers["X-CSRF-Token"] = issued.csrf_token if csrf == "valid" else csrf
    with TestClient(_protected_app(manager), base_url="http://127.0.0.1:8000") as client:
        response = client.post("/api/test/write", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == expected_code
    assert issued.session_id not in response.text
    assert issued.csrf_token not in response.text


def test_expired_cookie_has_distinct_error_and_is_not_renewed() -> None:
    now = {"value": 10.0}
    manager = InMemorySessionManager(
        ttl_seconds=5,
        max_entries=4,
        clock=lambda: now["value"],
    )
    issued = manager.issue()
    now["value"] = 15.0
    with TestClient(_protected_app(manager), base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/api/test/write",
            headers=_headers(
                issued.session_id,
                issued.csrf_token,
                origin="http://127.0.0.1:8000",
            ),
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"
    assert "set-cookie" not in response.headers


def test_duplicate_session_cookie_is_rejected_as_ambiguous() -> None:
    manager = InMemorySessionManager(ttl_seconds=60, max_entries=4)
    issued = manager.issue()
    headers = _headers(
        issued.session_id,
        issued.csrf_token,
        origin="http://127.0.0.1:8000",
    )
    headers["Cookie"] = f"aiwebnovel_session={issued.session_id}; aiwebnovel_session=ambiguous"
    with TestClient(_protected_app(manager), base_url="http://127.0.0.1:8000") as client:
        response = client.post("/api/test/write", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SESSION_REQUIRED"


def test_get_needs_no_csrf_and_options_is_unblocked() -> None:
    manager = InMemorySessionManager(ttl_seconds=60, max_entries=4)
    with TestClient(_protected_app(manager), base_url="http://127.0.0.1:8000") as client:
        get_response = client.get("/api/test/read", headers={"Host": "127.0.0.1:8000"})
        options_response = client.options(
            "/api/test/write",
            headers={"Host": "127.0.0.1:8000", "Origin": "https://external.example"},
        )
        external_health_like_get = client.get(
            "/api/test/read",
            headers={"Host": "127.0.0.1:8000", "Origin": "https://external.example"},
        )
    assert get_response.status_code == 200
    assert options_response.status_code == 200
    assert external_health_like_get.status_code == 200


def test_session_safe_endpoint_rejects_an_explicit_external_or_duplicate_origin() -> None:
    manager = InMemorySessionManager(ttl_seconds=60, max_entries=4)
    app = _protected_app(manager)

    @app.get("/api/v1/security/session")
    async def temporary_session() -> dict[str, bool]:
        return {"accepted": True}

    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        external = client.get(
            "/api/v1/security/session",
            headers={"Host": "127.0.0.1:8000", "Origin": "https://external.example"},
        )
        missing = client.get(
            "/api/v1/security/session",
            headers={"Host": "127.0.0.1:8000"},
        )
        duplicate = client.get(
            "/api/v1/security/session",
            headers=[
                ("Host", "127.0.0.1:8000"),
                ("Origin", "http://127.0.0.1:8000"),
                ("Origin", "https://external.example"),
            ],
        )
    assert external.status_code == 403
    assert external.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert missing.status_code == 200
    assert duplicate.status_code == 403
    assert duplicate.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


def test_csrf_digest_comparison_uses_constant_time_primitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = InMemorySessionManager(ttl_seconds=60, max_entries=4)
    issued = manager.issue()
    calls: list[tuple[object, object]] = []

    def checked_compare(left: object, right: object) -> bool:
        calls.append((left, right))
        return False

    monkeypatch.setattr("aiwebnovel.security.sessions.hmac.compare_digest", checked_compare)
    manager.validate_csrf(issued.session_id, "incorrect")
    assert len(calls) == 1
    assert all(isinstance(value, bytes) for value in calls[0])
