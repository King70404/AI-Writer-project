"""GET /projects/{id} current-snapshot contract tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import PROJECT_ID, isolated_app, snapshot

from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.web.dependencies import get_project_query_service

pytestmark = pytest.mark.integration


class RecordingQueryService:
    def __init__(self, result: object) -> None:
        self.result = result
        self.queries: list[GetProjectQuery] = []

    def get_project(self, query: GetProjectQuery):
        self.queries.append(query)
        return self.result


def test_get_requires_no_session_and_returns_current_etag(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingQueryService(snapshot(version=2, revision_number=2))
    app.dependency_overrides[get_project_query_service] = lambda: service

    with TestClient(app) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}")

    assert response.status_code == 200
    assert response.headers["ETag"] == '"2"'
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "head" not in response.json()
    assert "revisions" not in response.json()
    assert service.queries == [GetProjectQuery(PROJECT_ID)]


def test_get_missing_is_404_and_service_is_called_once(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingQueryService(None)
    app.dependency_overrides[get_project_query_service] = lambda: service

    with TestClient(app) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    assert len(service.queries) == 1


def test_get_invalid_id_maps_422_before_repository_access(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingQueryService(snapshot())
    app.dependency_overrides[get_project_query_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/api/v1/projects/not-a-project-id")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PROJECT_ID"
    assert service.queries == []
