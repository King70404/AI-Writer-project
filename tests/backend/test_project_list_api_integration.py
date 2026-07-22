"""Real migrated SQLite Project list HTTP pagination flow."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import issue_write_headers, migrated_api_app

pytestmark = pytest.mark.integration


def _sort_key(item: dict[str, object]) -> tuple[datetime, str]:
    return (datetime.fromisoformat(str(item["created_at"])), str(item["project_id"]))


def test_real_api_traverses_stably_across_revision_and_new_project(tmp_path: Path) -> None:
    with migrated_api_app(tmp_path) as (app, database_path), TestClient(app) as client:
        write_headers = issue_write_headers(client)
        created = [
            client.post(
                "/api/v1/projects",
                headers=write_headers,
                json={"title": f"Project {value}", "description": f"CANARY body {value}"},
            ).json()
            for value in range(5)
        ]
        expected = sorted(created, key=_sort_key, reverse=True)

        first = client.get("/api/v1/projects?limit=2")
        assert first.status_code == 200
        assert len(first.json()["items"]) == 2
        assert first.json()["next_cursor"]
        assert "description" not in first.text

        unread_id = str(expected[2]["project_id"])
        revised = client.put(
            f"/api/v1/projects/{unread_id}",
            headers={**write_headers, "If-Match": '"1"'},
            json={"title": "Revised during pagination", "description": "CANARY revised"},
        )
        assert revised.status_code == 200

        inserted = client.post(
            "/api/v1/projects",
            headers=write_headers,
            json={"title": "Newest Project", "description": "CANARY newest"},
        )
        assert inserted.status_code == 201
        inserted_id = inserted.json()["project_id"]

        observed = list(first.json()["items"])
        cursor = first.json()["next_cursor"]
        while cursor is not None:
            page = client.get("/api/v1/projects", params={"limit": "2", "cursor": cursor})
            assert page.status_code == 200
            observed.extend(page.json()["items"])
            cursor = page.json()["next_cursor"]

        observed_ids = [item["project_id"] for item in observed]
        expected_ids = [item["project_id"] for item in expected]
        assert observed_ids == expected_ids
        assert len(observed_ids) == len(set(observed_ids)) == 5
        assert inserted_id not in observed_ids
        revised_item = next(item for item in observed if item["project_id"] == unread_id)
        assert revised_item["title"] == "Revised during pagination"
        assert revised_item["concurrency_version"] == 2

        new_first = client.get("/api/v1/projects?limit=2")
        assert new_first.status_code == 200
        assert new_first.json()["items"][0]["project_id"] == inserted_id
        assert new_first.headers["Cache-Control"] == "no-store"

        invalid = client.get("/api/v1/projects?cursor=CANARY_CURSOR")
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "INVALID_CURSOR"
        assert "CANARY_CURSOR" not in invalid.text

        with closing(sqlite3.connect(database_path)) as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("projects", "project_revisions", "project_heads")
            }
        assert counts == {"projects": 6, "project_revisions": 7, "project_heads": 6}
