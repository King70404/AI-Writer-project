"""Real migrated SQLite Story Bible POST/GET/PUT HTTP integration flow."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.story_bible_http_support import (
    issue_write_headers,
    migrated_story_bible_api_app,
)

pytestmark = pytest.mark.integration


def test_real_story_bible_http_flow_preserves_revision_one_and_project(
    tmp_path: Path,
) -> None:
    with (
        migrated_story_bible_api_app(tmp_path) as (
            app,
            database_path,
        ),
        TestClient(app) as client,
    ):
        headers = issue_write_headers(client)
        project = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "Owning Project", "description": "Unchanged"},
        )
        assert project.status_code == 201
        project_id = project.json()["project_id"]
        project_revision_id = project.json()["current_revision_id"]

        created = client.post(
            f"/api/v1/projects/{project_id}/story-bible",
            headers=headers,
            json={"title": " Initial Bible ", "content": "Line A\r\nLine B"},
        )
        assert created.status_code == 201
        assert created.headers["ETag"] == '"1"'
        story_bible_id = created.json()["story_bible_id"]
        revision_one = created.json()["current_revision_id"]
        assert created.headers["Location"] == f"/api/v1/story-bibles/{story_bible_id}"
        assert created.json()["project_id"] == project_id
        assert created.json()["title"] == "Initial Bible"
        assert created.json()["content"] == "Line A\nLine B"

        nested = client.get(f"/api/v1/projects/{project_id}/story-bible")
        direct = client.get(f"/api/v1/story-bibles/{story_bible_id}")
        assert nested.status_code == direct.status_code == 200
        assert nested.json() == direct.json() == created.json()
        assert nested.headers["ETag"] == direct.headers["ETag"] == '"1"'

        revised = client.put(
            f"/api/v1/story-bibles/{story_bible_id}",
            headers={**headers, "If-Match": '"1"'},
            json={"title": "Replacement Bible", "content": ""},
        )
        assert revised.status_code == 200
        assert revised.headers["ETag"] == '"2"'
        assert revised.json()["revision_number"] == 2
        assert revised.json()["concurrency_version"] == 2
        assert revised.json()["title"] == "Replacement Bible"
        assert revised.json()["content"] == ""
        revision_two = revised.json()["current_revision_id"]

        current = client.get(f"/api/v1/story-bibles/{story_bible_id}")
        assert current.json() == revised.json()
        assert current.headers["ETag"] == '"2"'
        stale = client.put(
            f"/api/v1/story-bibles/{story_bible_id}",
            headers={**headers, "If-Match": '"1"'},
            json={
                "title": "STORY_BIBLE_HTTP_SECRET_CANARY",
                "content": "STORY_BIBLE_HTTP_SECRET_CANARY",
            },
        )
        assert stale.status_code == 412
        assert stale.json()["error"]["code"] == "STORY_BIBLE_VERSION_CONFLICT"
        assert "STORY_BIBLE_HTTP_SECRET_CANARY" not in stale.text

        with closing(sqlite3.connect(database_path)) as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "story_bibles",
                    "story_bible_revisions",
                    "story_bible_heads",
                )
            }
            revisions = connection.execute(
                "SELECT id, revision_number, title, content "
                "FROM story_bible_revisions ORDER BY revision_number"
            ).fetchall()
            head = connection.execute(
                "SELECT revision_id FROM story_bible_heads WHERE story_bible_id = ?",
                (story_bible_id,),
            ).fetchone()
            project_row = connection.execute(
                "SELECT concurrency_version FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            project_head = connection.execute(
                "SELECT revision_id FROM project_heads WHERE project_id = ?",
                (project_id,),
            ).fetchone()

        assert counts == {
            "story_bibles": 1,
            "story_bible_revisions": 2,
            "story_bible_heads": 1,
        }
        assert revisions == [
            (revision_one, 1, "Initial Bible", "Line A\nLine B"),
            (revision_two, 2, "Replacement Bible", ""),
        ]
        assert head == (revision_two,)
        assert project_row == (1,)
        assert project_head == (project_revision_id,)


def test_real_story_bible_http_distinguishes_both_nested_absence_cases(
    tmp_path: Path,
) -> None:
    with migrated_story_bible_api_app(tmp_path) as (app, _), TestClient(app) as client:
        headers = issue_write_headers(client)
        project = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "No Story Bible"},
        )
        project_id = project.json()["project_id"]
        absent = client.get(f"/api/v1/projects/{project_id}/story-bible")
        missing_project = client.get("/api/v1/projects/prj_00000000000000000000000001/story-bible")
    assert absent.status_code == missing_project.status_code == 404
    assert absent.json()["error"]["code"] == "STORY_BIBLE_FOR_PROJECT_NOT_FOUND"
    assert missing_project.json()["error"]["code"] == "PROJECT_NOT_FOUND"
