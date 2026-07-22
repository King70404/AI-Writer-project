"""Real migrated SQLite POST/GET/PUT Project HTTP integration flow."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import issue_write_headers, migrated_api_app

pytestmark = pytest.mark.integration


def test_real_migrated_project_api_flow_preserves_revisions_and_head(tmp_path: Path) -> None:
    with migrated_api_app(tmp_path) as (app, database_path), TestClient(app) as client:
        headers = issue_write_headers(client)
        created = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "Initial title", "description": "Initial description"},
        )
        assert created.status_code == 201
        assert created.headers["ETag"] == '"1"'
        project_id = created.json()["project_id"]
        revision_one = created.json()["current_revision_id"]
        assert created.headers["Location"] == f"/api/v1/projects/{project_id}"

        first_get = client.get(f"/api/v1/projects/{project_id}")
        assert first_get.status_code == 200
        assert first_get.json() == created.json()
        assert first_get.headers["ETag"] == '"1"'

        revised = client.put(
            f"/api/v1/projects/{project_id}",
            headers={**headers, "If-Match": '"1"'},
            json={"title": "Replacement title", "description": "Replacement description"},
        )
        assert revised.status_code == 200
        assert revised.headers["ETag"] == '"2"'
        assert revised.json()["revision_number"] == 2
        revision_two = revised.json()["current_revision_id"]

        second_get = client.get(f"/api/v1/projects/{project_id}")
        assert second_get.json() == revised.json()
        assert second_get.headers["ETag"] == '"2"'

        stale = client.put(
            f"/api/v1/projects/{project_id}",
            headers={**headers, "If-Match": '"1"'},
            json={"title": "CANARY stale", "description": "CANARY stale body"},
        )
        assert stale.status_code == 412
        assert stale.json()["error"]["code"] == "PROJECT_VERSION_CONFLICT"
        assert "CANARY" not in stale.text

        with closing(sqlite3.connect(database_path)) as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("projects", "project_revisions", "project_heads")
            }
            revisions = connection.execute(
                "SELECT id, revision_number, title, description FROM project_revisions "
                "ORDER BY revision_number"
            ).fetchall()
            head = connection.execute(
                "SELECT revision_id FROM project_heads WHERE project_id = ?", (project_id,)
            ).fetchone()

        assert counts == {"projects": 1, "project_revisions": 2, "project_heads": 1}
        assert revisions == [
            (revision_one, 1, "Initial title", "Initial description"),
            (revision_two, 2, "Replacement title", "Replacement description"),
        ]
        assert head == (revision_two,)


def test_two_apps_use_independent_migrated_databases(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    with migrated_api_app(first_root) as (first, first_path):
        with TestClient(first) as client:
            response = client.post(
                "/api/v1/projects",
                headers=issue_write_headers(client),
                json={"title": "Only first"},
            )
            assert response.status_code == 201
        with closing(sqlite3.connect(first_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1

    with migrated_api_app(second_root) as (second, second_path):
        with TestClient(second) as client:
            assert client.get("/api/v1/health/live").status_code == 200
        with closing(sqlite3.connect(second_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
