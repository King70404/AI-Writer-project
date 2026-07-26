"""Project immutable revision-history HTTP boundary tests."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import isolated_app

from aiwebnovel.project.application.models import (
    ProjectRevisionHistoryItem,
    ProjectRevisionHistoryPage,
    ProjectRevisionHistoryPosition,
    ProjectRevisionHistorySnapshot,
)
from aiwebnovel.project.application.queries import (
    GetProjectRevisionQuery,
    ListProjectRevisionsQuery,
)
from aiwebnovel.project.errors import (
    ProjectDataCorruption,
    ProjectNotFound,
    ProjectRepositoryError,
)
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.web.dependencies import (
    get_project_revision_history_query_service,
)
from aiwebnovel.project.web.revision_cursors import encode_project_revision_cursor

pytestmark = pytest.mark.unit

PROJECT_ID = "prj_00000000000000000000000001"
OTHER_PROJECT_ID = "prj_00000000000000000000000002"
REVISION_ID = "prv_00000000000000000000000003"
NOW = datetime(2026, 7, 3, 4, 5, 6, tzinfo=UTC)


def history_item(number: int = 1, *, current: bool = True) -> ProjectRevisionHistoryItem:
    return ProjectRevisionHistoryItem(
        REVISION_ID,
        number,
        f"Title {number}",
        NOW,
        current,
    )


def history_page(*, continuing: bool = False) -> ProjectRevisionHistoryPage:
    item = history_item()
    return ProjectRevisionHistoryPage(
        PROJECT_ID,
        1,
        (item,),
        ProjectRevisionHistoryPosition(PROJECT_ID, 1) if continuing else None,
        continuing,
    )


def history_snapshot(number: int = 1) -> ProjectRevisionHistorySnapshot:
    return ProjectRevisionHistorySnapshot(
        PROJECT_ID,
        REVISION_ID,
        number,
        f"Title {number}",
        "Original\nbody",
        NOW,
        number == 1,
        1,
    )


class RecordingHistoryService:
    def __init__(self, result: object) -> None:
        self.result = result
        self.list_queries: list[ListProjectRevisionsQuery] = []
        self.get_queries: list[GetProjectRevisionQuery] = []

    def list_revisions(
        self,
        query: ListProjectRevisionsQuery,
    ) -> ProjectRevisionHistoryPage:
        self.list_queries.append(query)
        if isinstance(self.result, Exception):
            raise self.result
        assert isinstance(self.result, ProjectRevisionHistoryPage)
        return self.result

    def get_revision(
        self,
        query: GetProjectRevisionQuery,
    ) -> ProjectRevisionHistorySnapshot | None:
        self.get_queries.append(query)
        if isinstance(self.result, Exception):
            raise self.result
        assert self.result is None or isinstance(self.result, ProjectRevisionHistorySnapshot)
        return self.result


def client_with_service(
    tmp_path: Path,
    service: RecordingHistoryService,
) -> TestClient:
    app = isolated_app(tmp_path)
    app.dependency_overrides[get_project_revision_history_query_service] = lambda: service
    return TestClient(app)


def test_list_maps_summary_default_limit_and_project_bound_cursor(tmp_path: Path) -> None:
    service = RecordingHistoryService(history_page(continuing=True))
    with client_with_service(tmp_path, service) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == PROJECT_ID
    assert body["current_revision_number"] == 1
    assert body["items"] == [
        {
            "revision_id": REVISION_ID,
            "revision_number": 1,
            "title": "Title 1",
            "created_at": "2026-07-03T04:05:06Z",
            "is_current": True,
        }
    ]
    assert "description" not in response.text
    assert "total" not in body
    assert body["next_cursor"]
    assert service.list_queries == [ListProjectRevisionsQuery(PROJECT_ID)]
    assert response.headers["Cache-Control"] == "no-store"
    assert "ETag" not in response.headers
    assert "Location" not in response.headers


@pytest.mark.parametrize("limit", ["1", "100"])
def test_list_accepts_limit_boundaries(tmp_path: Path, limit: str) -> None:
    service = RecordingHistoryService(history_page())
    with client_with_service(tmp_path, service) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions?limit={limit}")
    assert response.status_code == 200
    assert service.list_queries[0].limit == int(limit)


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=-1",
        "limit=101",
        "limit=1.0",
        "limit=true",
        "limit=1&limit=2",
        "offset=1",
        "sort=title",
        "search=x",
        "filter=current",
    ],
)
def test_invalid_list_query_is_422_without_service_call(
    tmp_path: Path,
    query: str,
) -> None:
    service = RecordingHistoryService(history_page())
    with client_with_service(tmp_path, service) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions?{query}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert service.list_queries == []


def test_valid_cursor_becomes_application_position(tmp_path: Path) -> None:
    position = ProjectRevisionHistoryPosition(PROJECT_ID, 7)
    cursor = encode_project_revision_cursor(position)
    service = RecordingHistoryService(history_page())
    with client_with_service(tmp_path, service) as client:
        response = client.get(
            f"/api/v1/projects/{PROJECT_ID}/revisions",
            params={"limit": "5", "cursor": cursor},
        )
    assert response.status_code == 200
    assert service.list_queries == [ListProjectRevisionsQuery(PROJECT_ID, 5, position)]


@pytest.mark.parametrize("cursor", ["", "CANARY_CURSOR", "abc=", "é"])
def test_invalid_cursor_is_safe_400_without_service_call(
    tmp_path: Path,
    cursor: str,
) -> None:
    service = RecordingHistoryService(history_page())
    with client_with_service(tmp_path, service) as client:
        response = client.get(
            f"/api/v1/projects/{PROJECT_ID}/revisions",
            params={"cursor": cursor},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REVISION_CURSOR"
    if cursor:
        assert cursor not in response.text
    assert service.list_queries == []


def test_cross_project_cursor_is_rejected_before_service(tmp_path: Path) -> None:
    cursor = encode_project_revision_cursor(ProjectRevisionHistoryPosition(OTHER_PROJECT_ID, 3))
    service = RecordingHistoryService(history_page())
    with client_with_service(tmp_path, service) as client:
        response = client.get(
            f"/api/v1/projects/{PROJECT_ID}/revisions",
            params={"cursor": cursor},
        )
    assert response.status_code == 400
    assert service.list_queries == []


def test_exact_revision_returns_complete_read_only_content(tmp_path: Path) -> None:
    service = RecordingHistoryService(history_snapshot())
    with client_with_service(tmp_path, service) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions/1")
    assert response.status_code == 200
    assert response.json() == {
        "project_id": PROJECT_ID,
        "revision_id": REVISION_ID,
        "revision_number": 1,
        "title": "Title 1",
        "description": "Original\nbody",
        "created_at": "2026-07-03T04:05:06Z",
        "is_current": True,
        "current_revision_number": 1,
    }
    assert service.get_queries == [GetProjectRevisionQuery(PROJECT_ID, 1)]
    assert response.headers["Cache-Control"] == "no-store"
    assert "ETag" not in response.headers


@pytest.mark.parametrize(
    "revision",
    ["0", "-1", "1.0", "1e0", "+1", "01", "%201", "true", "x", str(2**63)],
)
def test_noncanonical_revision_number_is_422_without_service_call(
    tmp_path: Path,
    revision: str,
) -> None:
    service = RecordingHistoryService(history_snapshot())
    with client_with_service(tmp_path, service) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions/{revision}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REVISION_NUMBER"
    assert service.get_queries == []


def test_invalid_project_id_precedes_cursor_and_revision_validation(tmp_path: Path) -> None:
    service = RecordingHistoryService(history_page())
    with client_with_service(tmp_path, service) as client:
        listing = client.get("/api/v1/projects/bad/revisions?cursor=CANARY")
        exact = client.get("/api/v1/projects/bad/revisions/0")
    assert listing.status_code == exact.status_code == 422
    assert listing.json()["error"]["code"] == "INVALID_PROJECT_ID"
    assert exact.json()["error"]["code"] == "INVALID_PROJECT_ID"
    assert service.list_queries == [] and service.get_queries == []


@pytest.mark.parametrize(
    ("result", "status", "code"),
    [
        (ProjectNotFound(ProjectId.parse(PROJECT_ID)), 404, "PROJECT_NOT_FOUND"),
        (ProjectDataCorruption(), 500, "PROJECT_DATA_CORRUPTION"),
        (ProjectRepositoryError(), 503, "PROJECT_PERSISTENCE_UNAVAILABLE"),
    ],
)
def test_known_history_failures_map_safely(
    tmp_path: Path,
    result: Exception,
    status: int,
    code: str,
) -> None:
    service = RecordingHistoryService(result)
    with client_with_service(tmp_path, service) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_missing_revision_has_distinct_404(tmp_path: Path) -> None:
    service = RecordingHistoryService(None)
    with client_with_service(tmp_path, service) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions/9")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_REVISION_NOT_FOUND"
    assert service.get_queries == [GetProjectRevisionQuery(PROJECT_ID, 9)]


def test_history_gets_need_no_session_origin_or_csrf(tmp_path: Path) -> None:
    service = RecordingHistoryService(history_page())
    with client_with_service(tmp_path, service) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_unmigrated_database_fails_safely_without_creating_schema(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        listing = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions")
        exact = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions/1")
        database_path = Path(app.state.database_engine.url.database)
    assert listing.status_code == exact.status_code == 503
    assert listing.json()["error"]["code"] == "PROJECT_PERSISTENCE_UNAVAILABLE"
    assert "no such table" not in listing.text.lower() + exact.text.lower()
    with closing(sqlite3.connect(database_path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert not tables.intersection({"projects", "project_heads", "project_revisions"})


def test_missing_history_service_returns_safe_503(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    with TestClient(app) as client:
        app.state.project_revision_history_query_service = None
        response = client.get(f"/api/v1/projects/{PROJECT_ID}/revisions")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROJECT_SERVICE_UNAVAILABLE"
