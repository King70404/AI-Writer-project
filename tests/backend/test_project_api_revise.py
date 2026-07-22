"""PUT /projects/{id} full-replacement and precondition tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import (
    PROJECT_ID,
    isolated_app,
    issue_write_headers,
    snapshot,
)

from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.project.application.commands import ReviseProjectCommand
from aiwebnovel.project.web.dependencies import get_project_command_service

pytestmark = pytest.mark.integration


class RecordingReviseService:
    def __init__(self, failure: Exception | None = None) -> None:
        self.commands: list[ReviseProjectCommand] = []
        self.failure = failure

    def revise_project(self, command: ReviseProjectCommand):
        self.commands.append(command)
        if self.failure is not None:
            raise self.failure
        return snapshot(version=2, revision_number=2)


def _put(client: TestClient, headers: dict[str, str], if_match: str | None):
    request_headers = dict(headers)
    if if_match is not None:
        request_headers["If-Match"] = if_match
    return client.put(
        f"/api/v1/projects/{PROJECT_ID}",
        headers=request_headers,
        json={"title": "Replacement", "description": "Complete replacement"},
    )


def test_revise_is_complete_replace_with_incremented_etag(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingReviseService()
    app.dependency_overrides[get_project_command_service] = lambda: service

    with TestClient(app) as client:
        response = _put(client, issue_write_headers(client), '"1"')

    assert response.status_code == 200
    assert response.headers["ETag"] == '"2"'
    assert service.commands == [
        ReviseProjectCommand(PROJECT_ID, 1, "Replacement", "Complete replacement")
    ]


def test_revise_requires_if_match_without_calling_service(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingReviseService()
    app.dependency_overrides[get_project_command_service] = lambda: service

    with TestClient(app) as client:
        response = _put(client, issue_write_headers(client), None)

    assert response.status_code == 428
    assert response.json()["error"]["code"] == "PRECONDITION_REQUIRED"
    assert service.commands == []


def test_revise_missing_if_match_precedes_invalid_body(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingReviseService()
    app.dependency_overrides[get_project_command_service] = lambda: service

    with TestClient(app) as client:
        headers = issue_write_headers(client)
        response = client.put(
            f"/api/v1/projects/{PROJECT_ID}",
            headers=headers,
            json={"title": 7},
        )

    assert response.status_code == 428
    assert response.json()["error"]["code"] == "PRECONDITION_REQUIRED"
    assert service.commands == []


@pytest.mark.parametrize("value", ["1", 'W/"1"', "*", '"1", "2"', '"0"'])
def test_revise_rejects_invalid_if_match_without_calling_service(
    tmp_path: Path, value: str
) -> None:
    app = isolated_app(tmp_path)
    service = RecordingReviseService()
    app.dependency_overrides[get_project_command_service] = lambda: service

    with TestClient(app) as client:
        response = _put(client, issue_write_headers(client), value)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IF_MATCH"
    assert service.commands == []


def test_revise_maps_stale_to_412_without_canary_echo(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingReviseService(ConcurrencyConflict(expected_version=1, actual_version=2))
    app.dependency_overrides[get_project_command_service] = lambda: service

    with TestClient(app) as client:
        response = _put(client, issue_write_headers(client), '"1"')

    assert response.status_code == 412
    assert response.json()["error"]["code"] == "PROJECT_VERSION_CONFLICT"
    assert response.json()["error"]["details"] == {
        "expected_version": 1,
        "actual_version": 2,
    }
    assert "Complete replacement" not in response.text


def test_revise_rejects_duplicate_if_match_headers(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = RecordingReviseService()
    app.dependency_overrides[get_project_command_service] = lambda: service

    with TestClient(app) as client:
        headers = issue_write_headers(client)
        response = client.put(
            f"/api/v1/projects/{PROJECT_ID}",
            headers=[
                *headers.items(),
                ("If-Match", '"1"'),
                ("If-Match", '"2"'),
            ],
            json={"title": "Replacement", "description": "Complete replacement"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IF_MATCH"
    assert service.commands == []
