"""Real migrated API flow for immutable Project revision history."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import issue_write_headers, migrated_api_app

pytestmark = pytest.mark.integration


def test_real_api_preserves_bodies_and_paginates_revision_numbers(tmp_path: Path) -> None:
    with migrated_api_app(tmp_path) as (app, database_path), TestClient(app) as client:
        headers = issue_write_headers(client)
        created = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "Original", "description": "Original body"},
        )
        assert created.status_code == 201
        project_id = created.json()["project_id"]
        first_revision_id = created.json()["current_revision_id"]
        second = client.put(
            f"/api/v1/projects/{project_id}",
            headers={**headers, "If-Match": '"1"'},
            json={"title": "Second", "description": "Second body"},
        )
        third = client.put(
            f"/api/v1/projects/{project_id}",
            headers={**headers, "If-Match": '"2"'},
            json={"title": "Third", "description": "Third body"},
        )
        assert second.status_code == third.status_code == 200

        first_page = client.get(f"/api/v1/projects/{project_id}/revisions?limit=2")
        assert first_page.status_code == 200
        assert [item["revision_number"] for item in first_page.json()["items"]] == [3, 2]
        assert [item["is_current"] for item in first_page.json()["items"]] == [True, False]
        assert "description" not in first_page.text
        cursor = first_page.json()["next_cursor"]
        final_page = client.get(
            f"/api/v1/projects/{project_id}/revisions",
            params={"limit": "2", "cursor": cursor},
        )
        assert [item["revision_number"] for item in final_page.json()["items"]] == [1]
        assert final_page.json()["next_cursor"] is None

        bodies = []
        for number in (1, 2, 3):
            response = client.get(f"/api/v1/projects/{project_id}/revisions/{number}")
            assert response.status_code == 200
            bodies.append((response.json()["title"], response.json()["description"]))
        assert bodies == [
            ("Original", "Original body"),
            ("Second", "Second body"),
            ("Third", "Third body"),
        ]

        fourth = client.put(
            f"/api/v1/projects/{project_id}",
            headers={**headers, "If-Match": '"3"'},
            json={"title": "Fourth", "description": "Fourth body"},
        )
        assert fourth.status_code == 200
        old_continuation = client.get(
            f"/api/v1/projects/{project_id}/revisions",
            params={"limit": "2", "cursor": cursor},
        )
        assert [item["revision_number"] for item in old_continuation.json()["items"]] == [1]
        refreshed = client.get(f"/api/v1/projects/{project_id}/revisions?limit=2")
        assert [item["revision_number"] for item in refreshed.json()["items"]] == [4, 3]

        with closing(sqlite3.connect(database_path)) as connection:
            revisions = connection.execute(
                "SELECT id, revision_number, title, description FROM project_revisions "
                "WHERE project_id = ? ORDER BY revision_number",
                (project_id,),
            ).fetchall()
            head = connection.execute(
                "SELECT revision_id FROM project_heads WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            triggers = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger'"
                ).fetchall()
            }
        assert len(revisions) == 4
        assert revisions[0] == (first_revision_id, 1, "Original", "Original body")
        assert head == fourth.json()["current_revision_id"]
        assert {
            "trg_project_revisions_no_update",
            "trg_project_revisions_no_delete",
        } <= triggers
