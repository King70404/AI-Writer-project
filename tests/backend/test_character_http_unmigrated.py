"""Character routes fail safely before migration 0004."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.character_http_support import (
    CHARACTER_ID,
    isolated_app,
    issue_write_headers,
)
from tests.backend.factories import create_test_settings
from tests.backend.project_api_support import create_test_app_from_settings
from tests.backend.test_story_bible_migration import (
    migrated_story_bible_database_context,
)

pytestmark = pytest.mark.integration


def _assert_reads_are_safe(client: TestClient, project_id: str) -> None:
    responses = (
        client.get(f"/api/v1/projects/{project_id}/characters"),
        client.get(f"/api/v1/characters/{CHARACTER_ID}"),
    )
    assert all(response.status_code == 503 for response in responses)
    assert all("sqlite" not in response.text.lower() for response in responses)


def _assert_writes_are_safe(client: TestClient, project_id: str) -> None:
    headers = issue_write_headers(client)
    responses = (
        client.post(
            f"/api/v1/projects/{project_id}/characters",
            headers=headers,
            json={"name": "A"},
        ),
        client.put(
            f"/api/v1/characters/{CHARACTER_ID}",
            headers={**headers, "If-Match": '"1"'},
            json={"name": "A", "role": "", "profile": ""},
        ),
    )
    assert all(response.status_code == 503 for response in responses)
    assert all("sqlite" not in response.text.lower() for response in responses)


def test_empty_database_character_reads_are_safe_503(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    with TestClient(app) as client:
        _assert_reads_are_safe(client, "prj_00000000000000000000000001")
        _assert_writes_are_safe(client, "prj_00000000000000000000000001")


def test_0003_database_character_routes_are_safe_503(tmp_path: Path) -> None:
    with migrated_story_bible_database_context(tmp_path) as database:
        app = create_test_app_from_settings(
            create_test_settings(
                data_root=(tmp_path / "character-0003-storage").resolve(),
                database_url=str(
                    URL.create(
                        "sqlite+pysqlite",
                        database=database.path.resolve().as_posix(),
                    )
                ),
            )
        )
        with TestClient(app) as client:
            headers = issue_write_headers(client)
            project = client.post(
                "/api/v1/projects",
                headers=headers,
                json={"title": "Existing owner"},
            )
            project_id = project.json()["project_id"]
            _assert_reads_are_safe(client, project_id)
            _assert_writes_are_safe(client, project_id)
