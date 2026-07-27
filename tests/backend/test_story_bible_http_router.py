"""Four Story Bible route contracts over recording application services."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.story_bible_http_support import (
    PROJECT_ID,
    STORY_BIBLE_ID,
    isolated_app,
    issue_write_headers,
    snapshot,
)

from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.story_bible.application.commands import (
    CreateStoryBibleCommand,
    ReviseStoryBibleCommand,
)
from aiwebnovel.story_bible.application.queries import (
    GetStoryBibleForProjectQuery,
    GetStoryBibleQuery,
)
from aiwebnovel.story_bible.web.dependencies import (
    get_story_bible_command_service,
    get_story_bible_query_service,
)

pytestmark = pytest.mark.integration


class RecordingCommandService:
    def __init__(self, *, revise_failure: Exception | None = None) -> None:
        self.create_commands: list[CreateStoryBibleCommand] = []
        self.revise_commands: list[ReviseStoryBibleCommand] = []
        self.revise_failure = revise_failure

    def create_story_bible(self, command: CreateStoryBibleCommand):
        self.create_commands.append(command)
        return snapshot()

    def revise_story_bible(self, command: ReviseStoryBibleCommand):
        self.revise_commands.append(command)
        if self.revise_failure is not None:
            raise self.revise_failure
        return snapshot(version=2, title=command.title, content=command.content)


class RecordingQueryService:
    def __init__(self) -> None:
        self.by_id: list[GetStoryBibleQuery] = []
        self.by_project: list[GetStoryBibleForProjectQuery] = []

    def get_story_bible(self, query: GetStoryBibleQuery):
        self.by_id.append(query)
        return snapshot()

    def get_story_bible_for_project(self, query: GetStoryBibleForProjectQuery):
        self.by_project.append(query)
        return snapshot()


def _app_with_services(tmp_path: Path):
    app = isolated_app(tmp_path)
    commands = RecordingCommandService()
    queries = RecordingQueryService()
    app.dependency_overrides[get_story_bible_command_service] = lambda: commands
    app.dependency_overrides[get_story_bible_query_service] = lambda: queries
    return app, commands, queries


def test_create_returns_201_location_etag_and_calls_command_once(tmp_path: Path) -> None:
    app, commands, queries = _app_with_services(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/story-bible",
            headers=issue_write_headers(client),
            json={"title": " Story Bible ", "content": "A\r\nB"},
        )
    assert response.status_code == 201
    assert response.headers["ETag"] == '"1"'
    assert response.headers["Location"] == f"/api/v1/story-bibles/{STORY_BIBLE_ID}"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]
    assert commands.create_commands == [
        CreateStoryBibleCommand(PROJECT_ID, " Story Bible ", "A\r\nB")
    ]
    assert commands.revise_commands == []
    assert queries.by_id == queries.by_project == []


def test_both_get_routes_return_same_snapshot_without_write_context(
    tmp_path: Path,
) -> None:
    app, commands, queries = _app_with_services(tmp_path)
    with TestClient(app) as client:
        nested = client.get(f"/api/v1/projects/{PROJECT_ID}/story-bible")
        direct = client.get(f"/api/v1/story-bibles/{STORY_BIBLE_ID}")
    assert nested.status_code == direct.status_code == 200
    assert nested.json() == direct.json()
    assert nested.headers["ETag"] == direct.headers["ETag"] == '"1"'
    assert nested.headers["Cache-Control"] == direct.headers["Cache-Control"] == "no-store"
    assert "Location" not in nested.headers
    assert "Location" not in direct.headers
    assert queries.by_project == [GetStoryBibleForProjectQuery(PROJECT_ID)]
    assert queries.by_id == [GetStoryBibleQuery(STORY_BIBLE_ID)]
    assert commands.create_commands == commands.revise_commands == []


def test_put_is_one_complete_replacement_with_new_etag(tmp_path: Path) -> None:
    app, commands, queries = _app_with_services(tmp_path)
    with TestClient(app) as client:
        response = client.put(
            f"/api/v1/story-bibles/{STORY_BIBLE_ID}",
            headers={**issue_write_headers(client), "If-Match": '"1"'},
            json={"title": "Replacement", "content": ""},
        )
    assert response.status_code == 200
    assert response.headers["ETag"] == '"2"'
    assert response.headers["Cache-Control"] == "no-store"
    assert "Location" not in response.headers
    assert response.json()["title"] == "Replacement"
    assert response.json()["content"] == ""
    assert commands.revise_commands == [
        ReviseStoryBibleCommand(STORY_BIBLE_ID, 1, "Replacement", "")
    ]
    assert commands.create_commands == []
    assert queries.by_id == queries.by_project == []


def test_put_stale_maps_safe_412_without_retry(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    commands = RecordingCommandService(
        revise_failure=ConcurrencyConflict(expected_version=1, actual_version=2)
    )
    app.dependency_overrides[get_story_bible_command_service] = lambda: commands
    canary = "STORY_BIBLE_HTTP_SECRET_CANARY"
    with TestClient(app) as client:
        response = client.put(
            f"/api/v1/story-bibles/{STORY_BIBLE_ID}",
            headers={**issue_write_headers(client), "If-Match": '"1"'},
            json={"title": canary, "content": canary},
        )
    assert response.status_code == 412
    assert response.json()["error"]["code"] == "STORY_BIBLE_VERSION_CONFLICT"
    assert response.json()["error"]["details"] == {
        "expected_version": 1,
        "actual_version": 2,
    }
    assert canary not in response.text
    assert len(commands.revise_commands) == 1


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/api/v1/projects/not-an-id/story-bible", "INVALID_PROJECT_ID"),
        ("/api/v1/story-bibles/not-an-id", "INVALID_STORY_BIBLE_ID"),
    ],
)
def test_invalid_path_ids_are_safe_and_do_not_call_services(
    tmp_path: Path,
    path: str,
    code: str,
) -> None:
    app, commands, queries = _app_with_services(tmp_path)
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert commands.create_commands == commands.revise_commands == []
    assert queries.by_id == queries.by_project == []
