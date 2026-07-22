"""POST /projects contract tests over an overridden application service."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import isolated_app, issue_write_headers, snapshot

from aiwebnovel.project.application.commands import CreateProjectCommand
from aiwebnovel.project.errors import InvalidProjectTitle
from aiwebnovel.project.web.dependencies import get_project_command_service

pytestmark = pytest.mark.integration


class RecordingCommandService:
    def __init__(self, failure: Exception | None = None) -> None:
        self.commands: list[CreateProjectCommand] = []
        self.failure = failure

    def create_project(self, command: CreateProjectCommand):
        self.commands.append(command)
        if self.failure is not None:
            raise self.failure
        return snapshot()


def test_create_returns_snapshot_location_etag_and_calls_once(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingCommandService()
    app.dependency_overrides[get_project_command_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects",
            headers=issue_write_headers(client),
            json={"title": "Project title", "description": "Project description"},
        )

    assert response.status_code == 201
    assert response.headers["Location"] == f"/api/v1/projects/{snapshot().project_id}"
    assert response.headers["ETag"] == '"1"'
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]
    assert response.json()["project_id"] == snapshot().project_id
    assert service.commands == [CreateProjectCommand("Project title", "Project description")]


def test_create_maps_domain_title_failure_without_body_echo(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingCommandService(InvalidProjectTitle())
    app.dependency_overrides[get_project_command_service] = lambda: service
    canary = "CANARY-INVALID-PROJECT-TITLE"

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects",
            headers=issue_write_headers(client),
            json={"title": canary},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PROJECT_TITLE"
    assert canary not in response.text
    assert len(service.commands) == 1
