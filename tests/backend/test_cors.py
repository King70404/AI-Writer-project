"""Strict local CORS policy tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

from aiwebnovel.core.config import Settings
from aiwebnovel.main import create_app

pytestmark = pytest.mark.integration


ALLOWED_ORIGIN = "http://127.0.0.1:5173"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        data_root=tmp_path / "storage",
        database_url=str(
            URL.create("sqlite+pysqlite", database=(tmp_path / "cors.sqlite3").as_posix())
        ),
    )


def test_allowed_origin_receives_only_the_configured_cors_policy(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health/live",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        preflight = client.options(
            "/api/v1/health/live",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Accept, X-Request-ID",
            },
        )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert response.headers["Access-Control-Expose-Headers"] == "X-Request-ID"
    assert "Access-Control-Allow-Credentials" not in response.headers
    assert response.headers["X-Request-ID"]

    assert preflight.status_code == 200
    assert preflight.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert "GET" in preflight.headers["Access-Control-Allow-Methods"]
    assert "OPTIONS" in preflight.headers["Access-Control-Allow-Methods"]
    assert "*" not in preflight.headers["Access-Control-Allow-Methods"]
    assert "*" not in preflight.headers["Access-Control-Allow-Headers"]
    assert "authorization" not in preflight.headers["Access-Control-Allow-Headers"].lower()
    assert "Access-Control-Allow-Credentials" not in preflight.headers


def test_unlisted_origin_and_unneeded_preflight_permissions_are_rejected(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))

    with TestClient(app) as client:
        unlisted = client.get(
            "/api/v1/health/live",
            headers={"Origin": "http://127.0.0.1:5999"},
        )
        method_preflight = client.options(
            "/api/v1/health/live",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
        header_preflight = client.options(
            "/api/v1/health/live",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

    assert unlisted.status_code == 200
    assert "Access-Control-Allow-Origin" not in unlisted.headers
    assert method_preflight.status_code == 400
    assert "POST" not in method_preflight.headers["Access-Control-Allow-Methods"]
    assert header_preflight.status_code == 400
    assert "authorization" not in header_preflight.headers["Access-Control-Allow-Headers"].lower()


def test_same_origin_style_request_does_not_depend_on_cors(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "Access-Control-Allow-Origin" not in response.headers
