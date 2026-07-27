"""Story Bible HTTP calls fail safely without the 0003 schema."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.factories import create_test_app
from tests.backend.story_bible_http_support import (
    PROJECT_ID,
    STORY_BIBLE_ID,
    issue_write_headers,
)

pytestmark = pytest.mark.integration

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_CONFIG = _REPOSITORY_ROOT / "backend" / "alembic.ini"


def _database_url(path: Path) -> str:
    return str(URL.create("sqlite+pysqlite", database=path.as_posix()))


def _upgrade_to_0002(database: Path, data_root: Path) -> None:
    environment = os.environ.copy()
    environment["AIWEBNOVEL_DATA_ROOT"] = str(data_root)
    environment["AIWEBNOVEL_DATABASE_URL"] = _database_url(database)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(_ALEMBIC_CONFIG),
            "upgrade",
            "0002_create_project_foundation",
        ],
        cwd=_REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _assert_story_calls_fail_503(client: TestClient, project_id: str) -> None:
    headers = issue_write_headers(client)
    calls = (
        client.post(
            f"/api/v1/projects/{project_id}/story-bible",
            headers=headers,
            json={"title": "Story Bible"},
        ),
        client.get(f"/api/v1/projects/{project_id}/story-bible"),
        client.get(f"/api/v1/story-bibles/{STORY_BIBLE_ID}"),
        client.put(
            f"/api/v1/story-bibles/{STORY_BIBLE_ID}",
            headers={**headers, "If-Match": '"1"'},
            json={"title": "Replacement", "content": ""},
        ),
    )
    assert all(response.status_code == 503 for response in calls)
    assert all(
        response.json()["error"]["code"] == "STORY_BIBLE_PERSISTENCE_UNAVAILABLE"
        for response in calls
    )


def test_empty_database_does_not_auto_migrate_and_live_remains_200(
    tmp_path: Path,
) -> None:
    database = (tmp_path / "empty.sqlite3").resolve()
    app = create_test_app(
        data_root=(tmp_path / "empty-storage").resolve(),
        database_url=_database_url(database),
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        _assert_story_calls_fail_503(client, PROJECT_ID)


def test_0002_database_does_not_auto_create_story_bible_tables(
    tmp_path: Path,
) -> None:
    database = (tmp_path / "project-only.sqlite3").resolve()
    storage = (tmp_path / "project-only-storage").resolve()
    _upgrade_to_0002(database, storage)
    app = create_test_app(data_root=storage, database_url=_database_url(database))
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        project = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "Project-only schema"},
        )
        assert project.status_code == 201
        _assert_story_calls_fail_503(client, project.json()["project_id"])
