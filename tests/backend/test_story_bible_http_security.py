"""Story Bible routes inherit the frozen local HTTP security baseline."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.story_bible_http_support import (
    ALLOWED_ORIGIN,
    PROJECT_ID,
    isolated_app,
    issue_write_headers,
    snapshot,
)

from aiwebnovel.story_bible.application.commands import CreateStoryBibleCommand
from aiwebnovel.story_bible.web.dependencies import get_story_bible_command_service

pytestmark = pytest.mark.integration


class CreateService:
    def __init__(self) -> None:
        self.commands: list[CreateStoryBibleCommand] = []

    def create_story_bible(self, command: CreateStoryBibleCommand):
        self.commands.append(command)
        return snapshot()


def test_post_requires_origin_session_and_csrf_before_service(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = CreateService()
    app.dependency_overrides[get_story_bible_command_service] = lambda: service
    path = f"/api/v1/projects/{PROJECT_ID}/story-bible"
    with TestClient(app) as client:
        no_origin = client.post(path, json={"title": "T"})
        session = client.get(
            "/api/v1/security/session",
            headers={"Origin": ALLOWED_ORIGIN},
        )
        no_csrf = client.post(path, headers={"Origin": ALLOWED_ORIGIN}, json={"title": "T"})
        bad_host = client.post(
            path,
            headers={
                "Origin": ALLOWED_ORIGIN,
                "X-CSRF-Token": str(session.json()["csrf_token"]),
                "Host": "external.invalid",
            },
            json={"title": "T"},
        )
    assert no_origin.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert no_csrf.json()["error"]["code"] == "CSRF_TOKEN_REQUIRED"
    assert bad_host.json()["error"]["code"] == "INVALID_HOST"
    assert service.commands == []


def test_post_rejects_non_json_oversize_and_invalid_shapes(tmp_path: Path) -> None:
    app = isolated_app(tmp_path, max_body_bytes=128)
    service = CreateService()
    app.dependency_overrides[get_story_bible_command_service] = lambda: service
    path = f"/api/v1/projects/{PROJECT_ID}/story-bible"
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        non_json = client.post(path, headers=headers, content=b"title=T")
        oversized = client.post(
            path,
            headers={**headers, "Content-Type": "application/json"},
            content=b'{"title":"' + (b"x" * 256) + b'"}',
        )
        array = client.post(path, headers=headers, json=["Title"])
        scalar = client.post(path, headers=headers, json="Title")
        extra = client.post(path, headers=headers, json={"title": "T", "project_id": PROJECT_ID})
        malformed = client.post(
            path,
            headers={**headers, "Content-Type": "application/json"},
            content=b'{"title":',
        )
        wrong_charset = client.post(
            path,
            headers={**headers, "Content-Type": "application/json; charset=latin-1"},
            content=b'{"title":"T"}',
        )
        missing_content_type = client.post(path, headers=headers, content=b"")
    assert non_json.status_code == 415
    assert non_json.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "REQUEST_TOO_LARGE"
    assert all(response.status_code == 422 for response in (array, scalar, extra, malformed))
    assert all(
        response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
        for response in (array, scalar, extra, malformed)
    )
    assert wrong_charset.status_code == 415
    assert wrong_charset.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert missing_content_type.status_code == 415
    assert missing_content_type.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert service.commands == []


def test_validation_and_domain_failures_do_not_echo_body_canary(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = CreateService()
    app.dependency_overrides[get_story_bible_command_service] = lambda: service
    canary = "STORY_BIBLE_HTTP_SECRET_CANARY"
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/story-bible",
            headers=issue_write_headers(client),
            json={"title": True, "content": canary},
        )
    assert response.status_code == 422
    assert canary not in response.text
    assert service.commands == []


def test_missing_or_wrong_composed_service_fails_safe_503(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    with TestClient(app) as client:
        app.state.story_bible_query_service = object()
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/story-bible")
        app.state.story_bible_command_service = object()
        write = client.post(
            f"/api/v1/projects/{PROJECT_ID}/story-bible",
            headers=issue_write_headers(client),
            json={"title": "T"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORY_BIBLE_SERVICE_UNAVAILABLE"
    assert "object" not in response.text
    assert write.status_code == 503
    assert write.json()["error"]["code"] == "STORY_BIBLE_SERVICE_UNAVAILABLE"
