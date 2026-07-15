"""Integrated application-factory tests for docs and security readiness."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aiwebnovel.core.config import Settings
from aiwebnovel.main import create_app
from aiwebnovel.security import RequestLimitsMiddleware

pytestmark = pytest.mark.integration


def _settings(tmp_path: Path, *, environment: str) -> Settings:
    return Settings(
        environment=environment,
        data_root=tmp_path / f"{environment}-security-application",
    )


def test_production_document_routes_are_closed_without_spa_fallback(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, environment="production")
    assert settings.expose_api_docs is False
    app = create_app(settings)

    with TestClient(app) as client:
        responses = [
            client.get(path, headers={"Accept": "text/html"})
            for path in (
                "/docs",
                "/docs/asset.js",
                "/redoc",
                "/redoc/asset.js",
                "/openapi.json",
                "/openapi.json/extra",
            )
        ]

    for response in responses:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
        assert "text/html" not in response.headers["content-type"]


def test_test_environment_docs_describe_only_non_authenticating_session(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, environment="test")
    app = create_app(settings)

    with TestClient(app) as client:
        docs = client.get("/docs")
        redoc = client.get("/redoc")
        schema_response = client.get("/openapi.json")

    assert docs.status_code == 200
    assert redoc.status_code == 200
    assert schema_response.status_code == 200
    assert "https://" not in docs.text
    assert "http://" not in docs.text
    assert "https://" not in redoc.text
    assert "http://" not in redoc.text
    assert "unsafe-inline" not in docs.headers["Content-Security-Policy"]
    operation = schema_response.json()["paths"]["/api/v1/security/session"]["get"]
    assert "not login" in operation["description"]
    assert str(settings.data_root) not in schema_response.text


def test_missing_security_middleware_fails_ready_but_not_live(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, environment="test"))
    app.user_middleware = [
        middleware
        for middleware in app.user_middleware
        if cast_middleware_class(middleware.cls) is not RequestLimitsMiddleware
    ]

    with TestClient(app) as client:
        live = client.get("/api/v1/health/live")
        ready = client.get("/api/v1/health/ready")

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json()["checks"]["security"] == "failed"
    assert str(tmp_path) not in ready.text


def test_versioned_api_prefix_keeps_session_and_request_boundaries(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        api_prefix="/api/v2",
        data_root=tmp_path / "versioned-api-security",
    )
    app = create_app(settings)

    with TestClient(app, base_url="http://127.0.0.1") as client:
        external_session = client.get(
            "/api/v2/security/session",
            headers={"Origin": "https://external.example"},
        )
        local_session = client.get(
            "/api/v2/security/session",
            headers={"Origin": "http://127.0.0.1"},
        )
        invalid_media = client.post(
            "/api/v2/missing",
            content=b"not-json",
            headers={"Content-Type": "text/plain"},
        )

    assert external_session.status_code == 403
    assert external_session.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert "set-cookie" not in external_session.headers
    assert local_session.status_code == 200
    assert "aiwebnovel_session=" in local_session.headers["set-cookie"]
    assert invalid_media.status_code == 415
    assert invalid_media.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert invalid_media.headers["Cache-Control"] == "no-store"


def cast_middleware_class(value: object) -> object:
    """Keep Starlette's generic middleware factory typing out of identity checks."""
    return value
