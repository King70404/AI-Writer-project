"""Security middleware, CORS, and missing-service behavior for Project routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import (
    ALLOWED_ORIGIN,
    PROJECT_ID,
    isolated_app,
    issue_write_headers,
    snapshot,
)

from aiwebnovel.project.web.dependencies import get_project_command_service

pytestmark = pytest.mark.integration


class SuccessfulService:
    def create_project(self, command: object):
        return snapshot()


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ({}, "ORIGIN_NOT_ALLOWED"),
        ({"Origin": "http://127.0.0.1:5999"}, "ORIGIN_NOT_ALLOWED"),
        ({"Origin": ALLOWED_ORIGIN}, "SESSION_REQUIRED"),
    ],
)
def test_post_rejects_missing_security_inputs(
    tmp_path: Path, headers: dict[str, str], code: str
) -> None:
    app = isolated_app(tmp_path)
    app.dependency_overrides[get_project_command_service] = lambda: SuccessfulService()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "Title"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == code


def test_post_rejects_missing_and_wrong_csrf(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    app.dependency_overrides[get_project_command_service] = lambda: SuccessfulService()

    with TestClient(app) as client:
        session = client.get(
            "/api/v1/security/session",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        missing = client.post(
            "/api/v1/projects",
            headers={"Origin": ALLOWED_ORIGIN},
            json={"title": "Title"},
        )
        wrong = client.post(
            "/api/v1/projects",
            headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "wrong"},
            json={"title": "Title"},
        )

    assert session.status_code == 200
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "CSRF_TOKEN_REQUIRED"
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_post_rejects_non_json_and_oversized_body(tmp_path: Path) -> None:
    app = isolated_app(tmp_path, max_body_bytes=64)
    app.dependency_overrides[get_project_command_service] = lambda: SuccessfulService()

    with TestClient(app) as client:
        session = client.get(
            "/api/v1/security/session",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        secure = {
            "Origin": ALLOWED_ORIGIN,
            "X-CSRF-Token": session.json()["csrf_token"],
        }
        wrong_type = client.post(
            "/api/v1/projects",
            headers={**secure, "Content-Type": "text/plain"},
            content="not json",
        )
        oversized = client.post(
            "/api/v1/projects",
            headers=secure,
            json={"title": "T", "description": "x" * 128},
        )

    assert wrong_type.status_code == 415
    assert oversized.status_code == 413


def test_project_service_absence_returns_safe_503(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    app.state.project_query_service = None

    with TestClient(app) as client:
        app.state.project_query_service = None
        response = client.get(f"/api/v1/projects/{PROJECT_ID}")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROJECT_SERVICE_UNAVAILABLE"
    assert "state" not in response.text.lower()


def test_project_command_service_absence_returns_safe_503(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)

    with TestClient(app) as client:
        headers = issue_write_headers(client)
        app.state.project_command_service = None
        response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "Title"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROJECT_SERVICE_UNAVAILABLE"


def test_project_cors_preflight_is_explicit_and_rejects_extra_permissions(
    tmp_path: Path,
) -> None:
    app = isolated_app(tmp_path)

    with TestClient(app) as client:
        allowed = client.options(
            "/api/v1/projects",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": (
                    "Content-Type, X-CSRF-Token, If-Match, X-Request-ID"
                ),
            },
        )
        denied_method = client.options(
            "/api/v1/projects",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "PATCH",
            },
        )
        denied_header = client.options(
            "/api/v1/projects",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Methods"] == "GET, POST, PUT, OPTIONS"
    assert "if-match" in allowed.headers["Access-Control-Allow-Headers"].lower()
    assert denied_method.status_code == 400
    assert denied_header.status_code == 400
