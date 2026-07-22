"""Project list HTTP boundary, security, and safe failure tests."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import isolated_app

from aiwebnovel.project.application.models import (
    ProjectListItem,
    ProjectListPage,
    ProjectListPosition,
)
from aiwebnovel.project.application.queries import ListProjectsQuery
from aiwebnovel.project.errors import ProjectDataCorruption, ProjectRepositoryError
from aiwebnovel.project.web.cursors import encode_project_list_cursor
from aiwebnovel.project.web.dependencies import get_project_list_query_service

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 2, 3, 4, 5, tzinfo=UTC)
PROJECT_ID = "prj_00000000000000000000000001"
REVISION_ID = "prv_00000000000000000000000002"


def list_item(*, title: str = "List title") -> ProjectListItem:
    return ProjectListItem(
        project_id=PROJECT_ID,
        current_revision_id=REVISION_ID,
        revision_number=1,
        concurrency_version=1,
        title=title,
        created_at=NOW,
        updated_at=NOW,
        revision_created_at=NOW,
    )


class RecordingListService:
    def __init__(self, result: ProjectListPage | Exception) -> None:
        self.result = result
        self.queries: list[ListProjectsQuery] = []

    def list_projects(self, query: ListProjectsQuery) -> ProjectListPage:
        self.queries.append(query)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _client_with_service(
    tmp_path: Path,
    service: RecordingListService,
) -> tuple[object, TestClient]:
    app = isolated_app(tmp_path)
    app.dependency_overrides[get_project_list_query_service] = lambda: service
    return app, TestClient(app)


def test_empty_list_returns_canonical_response_and_default_limit(tmp_path: Path) -> None:
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get("/api/v1/projects")

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None, "has_more": False}
    assert service.queries == [ListProjectsQuery(limit=20)]


def test_list_maps_summary_and_next_cursor_without_description(tmp_path: Path) -> None:
    item = list_item()
    position = ProjectListPosition(created_at=item.created_at, project_id=item.project_id)
    service = RecordingListService(
        ProjectListPage(items=(item,), next_position=position, has_more=True)
    )
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get("/api/v1/projects?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [
        {
            "project_id": PROJECT_ID,
            "current_revision_id": REVISION_ID,
            "revision_number": 1,
            "concurrency_version": 1,
            "title": "List title",
            "created_at": "2026-06-02T03:04:05Z",
            "updated_at": "2026-06-02T03:04:05Z",
            "revision_created_at": "2026-06-02T03:04:05Z",
        }
    ]
    assert "description" not in response.text
    assert body["next_cursor"] == encode_project_list_cursor(position)
    assert body["has_more"] is True
    assert service.queries == [ListProjectsQuery(limit=1)]


@pytest.mark.parametrize("limit", ["1", "100"])
def test_limit_boundaries_are_accepted(tmp_path: Path, limit: str) -> None:
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get(f"/api/v1/projects?limit={limit}")
    assert response.status_code == 200
    assert service.queries[0].limit == int(limit)


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=-1",
        "limit=101",
        "limit=1.0",
        "limit=",
        "limit=true",
        "limit=1&limit=2",
        "offset=1",
        "search=title",
        "sort=title",
    ],
)
def test_invalid_or_unsupported_query_returns_safe_422_without_service_call(
    tmp_path: Path,
    query: str,
) -> None:
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get(f"/api/v1/projects?{query}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert query not in response.text
    assert service.queries == []


def test_invalid_limit_is_rejected_before_cursor_decoder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(_cursor: object) -> object:
        raise AssertionError("cursor decoder must not run")

    monkeypatch.setattr(
        "aiwebnovel.project.web.dependencies.decode_project_list_cursor",
        fail_if_called,
    )
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get("/api/v1/projects?limit=0&cursor=CANARY_CURSOR")
    assert response.status_code == 422
    assert "CANARY_CURSOR" not in response.text
    assert service.queries == []


@pytest.mark.parametrize(
    "cursor",
    ["", "CANARY_SECRET", "abc=", "é"],
)
def test_invalid_cursor_returns_safe_400_without_calling_service(
    tmp_path: Path,
    cursor: str,
) -> None:
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get("/api/v1/projects", params={"cursor": cursor})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"
    if cursor:
        assert cursor not in response.text
    assert service.queries == []


def test_duplicate_cursor_is_rejected_without_calling_service(tmp_path: Path) -> None:
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get("/api/v1/projects?cursor=first&cursor=second")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"
    assert service.queries == []


def test_valid_cursor_becomes_application_position(tmp_path: Path) -> None:
    position = ProjectListPosition(created_at=NOW, project_id=PROJECT_ID)
    cursor = encode_project_list_cursor(position)
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get("/api/v1/projects", params={"limit": "7", "cursor": cursor})
    assert response.status_code == 200
    assert service.queries == [ListProjectsQuery(limit=7, after=position)]


def test_list_needs_no_session_origin_or_csrf_and_has_security_headers(tmp_path: Path) -> None:
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get("/api/v1/projects")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "ETag" not in response.headers
    assert "Location" not in response.headers


def test_external_host_is_rejected_before_list_service(tmp_path: Path) -> None:
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get("/api/v1/projects", headers={"Host": "evil.example"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_HOST"
    assert service.queries == []


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (ProjectDataCorruption(), 500, "PROJECT_DATA_CORRUPTION"),
        (ProjectRepositoryError(), 503, "PROJECT_PERSISTENCE_UNAVAILABLE"),
    ],
)
def test_known_list_failures_use_safe_error_mapping(
    tmp_path: Path,
    failure: Exception,
    status: int,
    code: str,
) -> None:
    service = RecordingListService(failure)
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.get("/api/v1/projects?cursor=CANARY")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"
    assert service.queries == []

    valid_service = RecordingListService(failure)
    _app, client = _client_with_service(tmp_path / code, valid_service)
    with client:
        response = client.get("/api/v1/projects")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "CANARY" not in response.text
    assert len(valid_service.queries) == 1


def test_missing_list_service_returns_safe_503(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    with TestClient(app) as client:
        app.state.project_list_query_service = None
        response = client.get("/api/v1/projects")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROJECT_SERVICE_UNAVAILABLE"


def test_unmigrated_database_fails_503_without_auto_creating_project_schema(
    tmp_path: Path,
) -> None:
    app = isolated_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        response = client.get("/api/v1/projects")
        database_path = Path(app.state.database_engine.url.database)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROJECT_PERSISTENCE_UNAVAILABLE"
    assert "no such table" not in response.text.lower()
    with closing(sqlite3.connect(database_path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert not tables.intersection({"projects", "project_heads", "project_revisions"})


def test_get_request_body_does_not_change_list_query(tmp_path: Path) -> None:
    service = RecordingListService(ProjectListPage(items=(), next_position=None, has_more=False))
    _app, client = _client_with_service(tmp_path, service)
    with client:
        response = client.request(
            "GET",
            "/api/v1/projects",
            content='{"limit": 1, "search": "ignored"}',
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 200
    assert service.queries == [ListProjectsQuery(limit=20)]


def test_mapper_rejects_non_page_and_dto_timestamps_are_utc() -> None:
    from aiwebnovel.project.web.dto import ProjectListItemResponse
    from aiwebnovel.project.web.mappers import project_list_response_from_page

    with pytest.raises(TypeError):
        project_list_response_from_page(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProjectListItemResponse(
            project_id=PROJECT_ID,
            current_revision_id=REVISION_ID,
            revision_number=1,
            concurrency_version=1,
            title="Title",
            created_at=NOW.replace(tzinfo=None),
            updated_at=NOW,
            revision_created_at=NOW,
        )
