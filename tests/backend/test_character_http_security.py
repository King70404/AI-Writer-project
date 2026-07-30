"""Character write security and transport limits."""

from pathlib import Path

from fastapi.testclient import TestClient
from tests.backend.character_http_support import (
    ALLOWED_ORIGIN,
    PROJECT_ID,
    isolated_app,
)


def test_writes_require_session_origin_csrf_and_json(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    with TestClient(app) as client:
        path = f"/api/v1/projects/{PROJECT_ID}/characters"
        missing_session = client.post(path, json={"name": "A"})
        session = client.get(
            "/api/v1/security/session",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        csrf = str(session.json()["csrf_token"])
        wrong_origin = client.post(
            path,
            headers={"Origin": "https://invalid.example", "X-CSRF-Token": csrf},
            json={"name": "A"},
        )
        missing_csrf = client.post(
            path,
            headers={"Origin": ALLOWED_ORIGIN},
            json={"name": "A"},
        )
        bad_media = client.post(
            path,
            headers={
                "Origin": ALLOWED_ORIGIN,
                "X-CSRF-Token": csrf,
                "Content-Type": "text/plain",
            },
            content="{}",
        )
    assert missing_session.status_code == 403
    assert wrong_origin.status_code == 403
    assert missing_csrf.status_code == 403
    assert bad_media.status_code == 415


def test_reads_need_no_session_origin_or_csrf(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/characters")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CHARACTER_PERSISTENCE_UNAVAILABLE"


def test_character_body_uses_shared_one_mib_limit(tmp_path: Path) -> None:
    app = isolated_app(tmp_path, max_body_bytes=32)
    with TestClient(app) as client:
        session = client.get(
            "/api/v1/security/session",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/characters",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "X-CSRF-Token": str(session.json()["csrf_token"]),
            },
            json={"name": "A" * 40},
        )
    assert response.status_code == 413
