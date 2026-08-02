"""Migrated SQLite integration for immutable Character revision-history HTTP."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.character_http_support import (
    issue_write_headers,
    migrated_character_api_app,
)

pytestmark = pytest.mark.integration


def test_history_list_keyset_and_on_demand_body_reads(tmp_path: Path) -> None:
    with (
        migrated_character_api_app(tmp_path) as (app, _),
        TestClient(app) as client,
    ):
        headers = issue_write_headers(client)
        project = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "History owner"},
        )
        project_id = project.json()["project_id"]
        created = client.post(
            f"/api/v1/projects/{project_id}/characters",
            headers=headers,
            json={"name": "Revision 1", "role": "Lead", "profile": "Body 1"},
        )
        character_id = created.json()["character_id"]
        etag = created.headers["ETag"]
        for number in (2, 3):
            revised = client.put(
                f"/api/v1/characters/{character_id}",
                headers={**headers, "If-Match": etag},
                json={
                    "name": f"Revision {number}",
                    "role": "Lead",
                    "profile": f"Body {number}",
                },
            )
            assert revised.status_code == 200
            etag = revised.headers["ETag"]

        first = client.get(f"/api/v1/characters/{character_id}/revisions?limit=2")
        assert first.status_code == 200
        assert first.headers["Cache-Control"] == "no-store"
        assert "ETag" not in first.headers
        assert [item["revision_number"] for item in first.json()["items"]] == [
            3,
            2,
        ]
        assert all("profile" not in item for item in first.json()["items"])
        assert first.json()["has_more"] is True
        cursor = first.json()["next_cursor"]

        second = client.get(
            f"/api/v1/characters/{character_id}/revisions",
            params={"limit": "2", "cursor": cursor},
        )
        assert [item["revision_number"] for item in second.json()["items"]] == [1]
        assert second.json()["next_cursor"] is None
        assert second.json()["has_more"] is False

        historical = client.get(f"/api/v1/characters/{character_id}/revisions/1")
        current = client.get(f"/api/v1/characters/{character_id}/revisions/3")
        assert historical.json()["profile"] == "Body 1"
        assert historical.json()["is_current"] is False
        assert historical.json()["current_revision_number"] == 3
        assert current.json()["profile"] == "Body 3"
        assert current.json()["is_current"] is True
        assert current.headers["Cache-Control"] == "no-store"


def test_history_api_strict_failures_are_safe_and_read_only(tmp_path: Path) -> None:
    with (
        migrated_character_api_app(tmp_path) as (app, _),
        TestClient(app) as client,
    ):
        headers = issue_write_headers(client)
        project = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "Strict owner"},
        )
        project_id = project.json()["project_id"]
        created = client.post(
            f"/api/v1/projects/{project_id}/characters",
            headers=headers,
            json={"name": "Only revision", "role": "Lead", "profile": "Private body"},
        )
        character_id = created.json()["character_id"]
        good = client.get(f"/api/v1/characters/{character_id}/revisions?limit=1")
        cursor = good.json()["next_cursor"]
        assert cursor is None

        cases = [
            client.get(f"/api/v1/characters/{character_id}/revisions?limit=0"),
            client.get(f"/api/v1/characters/{character_id}/revisions?limit=01"),
            client.get(f"/api/v1/characters/{character_id}/revisions?extra=1"),
            client.get(f"/api/v1/characters/{character_id}/revisions?cursor=bad"),
            client.get(f"/api/v1/characters/{character_id}/revisions/01"),
            client.get(f"/api/v1/characters/{character_id}/revisions/999"),
        ]
        assert [response.status_code for response in cases] == [
            422,
            422,
            422,
            400,
            422,
            404,
        ]
        assert "Private body" not in "".join(response.text for response in cases)
        assert cases[-1].json()["error"]["code"] == ("CHARACTER_REVISION_NOT_FOUND")

        current = client.get(f"/api/v1/characters/{character_id}")
        assert current.json()["revision_number"] == 1
        assert current.json()["profile"] == "Private body"
