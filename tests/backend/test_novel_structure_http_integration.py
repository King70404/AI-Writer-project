"""Real migrated Outline, Volume, and Chapter HTTP workflow."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.character_http_support import issue_write_headers
from tests.backend.factories import create_test_settings
from tests.backend.novel_structure_repository_support import (
    chapter_id as deterministic_chapter_id,
)
from tests.backend.novel_structure_repository_support import (
    outline_id as deterministic_outline_id,
)
from tests.backend.novel_structure_repository_support import (
    project_id as deterministic_project_id,
)
from tests.backend.novel_structure_repository_support import (
    volume_id as deterministic_volume_id,
)
from tests.backend.project_api_support import create_test_app_from_settings
from tests.backend.test_novel_structure_migration import (
    migrated_novel_structure_database_context,
)

pytestmark = pytest.mark.integration


def test_real_http_complete_outline_volume_chapter_flow(tmp_path: Path) -> None:
    with migrated_novel_structure_database_context(tmp_path) as database:
        app = create_test_app_from_settings(
            create_test_settings(
                data_root=(tmp_path / "novel-structure-http-storage").resolve(),
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
                json={"title": "Novel structure owner"},
            )
            second_project = client.post(
                "/api/v1/projects",
                headers=headers,
                json={"title": "Other owner"},
            )
            project_id = project.json()["project_id"]
            other_project_id = second_project.json()["project_id"]

            outline = client.post(
                f"/api/v1/projects/{project_id}/outline",
                headers=headers,
                json={"title": "  Master Outline  ", "summary": "line 1\r\nline 2"},
            )
            duplicate_outline = client.post(
                f"/api/v1/projects/{project_id}/outline",
                headers=headers,
                json={"title": "Duplicate", "summary": ""},
            )
            volume_two = client.post(
                f"/api/v1/projects/{project_id}/volumes",
                headers=headers,
                json={"title": "Volume Two", "summary": "", "position": 2},
            )
            volume_one = client.post(
                f"/api/v1/projects/{project_id}/volumes",
                headers=headers,
                json={"title": "Volume One", "summary": "", "position": 1},
            )
            duplicate_volume_position = client.post(
                f"/api/v1/projects/{project_id}/volumes",
                headers=headers,
                json={"title": "Conflict", "summary": "", "position": 1},
            )
            volume_id = volume_one.json()["volume_id"]
            chapter_two = client.post(
                f"/api/v1/projects/{project_id}/volumes/{volume_id}/chapters",
                headers=headers,
                json={"title": "Chapter Two", "summary": "", "position": 2},
            )
            chapter_one = client.post(
                f"/api/v1/projects/{project_id}/volumes/{volume_id}/chapters",
                headers=headers,
                json={"title": "Chapter One", "summary": "", "position": 1},
            )
            duplicate_chapter_position = client.post(
                f"/api/v1/projects/{project_id}/volumes/{volume_id}/chapters",
                headers=headers,
                json={"title": "Conflict", "summary": "", "position": 1},
            )
            cross_owner_create = client.post(
                f"/api/v1/projects/{other_project_id}/volumes/{volume_id}/chapters",
                headers=headers,
                json={"title": "Wrong owner", "summary": "", "position": 3},
            )
            cross_owner_list = client.get(
                f"/api/v1/projects/{other_project_id}/volumes/{volume_id}/chapters"
            )

            outline_read = client.get(f"/api/v1/projects/{project_id}/outline")
            volumes = client.get(f"/api/v1/projects/{project_id}/volumes")
            volume_read = client.get(f"/api/v1/volumes/{volume_id}")
            chapters = client.get(f"/api/v1/projects/{project_id}/volumes/{volume_id}/chapters")
            chapter_id = chapter_one.json()["chapter_id"]
            chapter_read = client.get(f"/api/v1/chapters/{chapter_id}")

            outline_update = client.put(
                f"/api/v1/outlines/{outline.json()['outline_id']}",
                headers={**headers, "If-Match": outline.headers["ETag"]},
                json={"title": "Revised Outline", "summary": "replacement"},
            )
            volume_update = client.put(
                f"/api/v1/volumes/{volume_id}",
                headers={**headers, "If-Match": volume_one.headers["ETag"]},
                json={"title": "Revised Volume", "summary": "replacement", "position": 3},
            )
            chapter_update = client.put(
                f"/api/v1/chapters/{chapter_id}",
                headers={**headers, "If-Match": chapter_one.headers["ETag"]},
                json={"title": "Revised Chapter", "summary": "replacement", "position": 3},
            )
            stale_outline = client.put(
                f"/api/v1/outlines/{outline.json()['outline_id']}",
                headers={**headers, "If-Match": outline.headers["ETag"]},
                json={"title": "Stale Outline", "summary": "must not persist"},
            )
            stale_volume = client.put(
                f"/api/v1/volumes/{volume_id}",
                headers={**headers, "If-Match": volume_one.headers["ETag"]},
                json={"title": "Stale Volume", "summary": "", "position": 4},
            )
            stale = client.put(
                f"/api/v1/chapters/{chapter_id}",
                headers={**headers, "If-Match": chapter_one.headers["ETag"]},
                json={"title": "Stale", "summary": "must not persist", "position": 4},
            )
            duplicate_volume_update = client.put(
                f"/api/v1/volumes/{volume_two.json()['volume_id']}",
                headers={**headers, "If-Match": volume_two.headers["ETag"]},
                json={"title": "Volume Two", "summary": "", "position": 3},
            )
            duplicate_chapter_update = client.put(
                f"/api/v1/chapters/{chapter_two.json()['chapter_id']}",
                headers={**headers, "If-Match": chapter_two.headers["ETag"]},
                json={"title": "Chapter Two", "summary": "", "position": 3},
            )

            missing_project_id = str(deterministic_project_id(99_999))
            missing_outline_id = str(deterministic_outline_id(99_999))
            missing_volume_id = str(deterministic_volume_id(99_999))
            missing_chapter_id = str(deterministic_chapter_id(99_999))
            missing_project_outline = client.post(
                f"/api/v1/projects/{missing_project_id}/outline",
                headers=headers,
                json={"title": "Missing owner", "summary": ""},
            )
            missing_project_volumes = client.get(f"/api/v1/projects/{missing_project_id}/volumes")
            missing_outline_for_project = client.get(f"/api/v1/projects/{other_project_id}/outline")
            missing_outline = client.put(
                f"/api/v1/outlines/{missing_outline_id}",
                headers={**headers, "If-Match": '"1"'},
                json={"title": "Missing", "summary": ""},
            )
            missing_volume = client.get(f"/api/v1/volumes/{missing_volume_id}")
            missing_volume_chapter = client.post(
                f"/api/v1/projects/{project_id}/volumes/{missing_volume_id}/chapters",
                headers=headers,
                json={"title": "Missing volume", "summary": "", "position": 1},
            )
            missing_chapter = client.get(f"/api/v1/chapters/{missing_chapter_id}")
            invalid_outline = client.post(
                f"/api/v1/projects/{project_id}/outline",
                headers=headers,
                json={"title": "", "summary": ""},
            )
            invalid_volume = client.post(
                f"/api/v1/projects/{project_id}/volumes",
                headers=headers,
                json={"title": "Invalid", "summary": "", "position": True},
            )
            missing_if_match = client.put(
                f"/api/v1/chapters/{chapter_id}",
                headers=headers,
                json={"title": "No precondition", "summary": "", "position": 4},
            )

        assert project.status_code == second_project.status_code == 201
        assert outline.status_code == volume_one.status_code == volume_two.status_code == 201
        assert chapter_one.status_code == chapter_two.status_code == 201
        assert duplicate_chapter_position.status_code == 409
        assert outline.json()["title"] == "Master Outline"
        assert outline.json()["summary"] == "line 1\nline 2"
        assert outline.headers["ETag"] == volume_one.headers["ETag"] == '"1"'
        assert duplicate_outline.status_code == 409
        assert duplicate_volume_position.status_code == 409
        assert cross_owner_create.status_code == cross_owner_list.status_code == 409
        assert outline_read.json() == outline.json()
        assert [item["position"] for item in volumes.json()] == [1, 2]
        assert volume_read.json() == volume_one.json()
        assert [item["position"] for item in chapters.json()] == [1, 2]
        assert chapter_read.json() == chapter_one.json()
        assert outline_update.headers["ETag"] == '"2"'
        assert volume_update.headers["ETag"] == '"2"'
        assert chapter_update.headers["ETag"] == '"2"'
        assert outline_update.json()["summary"] == "replacement"
        assert volume_update.json()["position"] == chapter_update.json()["position"] == 3
        assert outline_update.json()["revision_number"] == 2
        assert volume_update.json()["revision_number"] == 2
        assert chapter_update.json()["revision_number"] == 2
        assert stale_outline.status_code == stale_volume.status_code == stale.status_code == 412
        assert stale.json()["error"]["details"] == {
            "expected_version": 1,
            "actual_version": 2,
        }
        assert duplicate_volume_update.status_code == duplicate_chapter_update.status_code == 409
        assert missing_project_outline.status_code == missing_project_volumes.status_code == 404
        assert missing_outline_for_project.status_code == missing_outline.status_code == 404
        assert missing_volume.status_code == missing_volume_chapter.status_code == 404
        assert missing_chapter.status_code == 404
        assert invalid_outline.status_code == invalid_volume.status_code == 422
        assert missing_if_match.status_code == 428

        with closing(sqlite3.connect(database.path)) as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "outlines",
                    "outline_revisions",
                    "outline_heads",
                    "volumes",
                    "volume_revisions",
                    "volume_heads",
                    "chapters",
                    "chapter_revisions",
                    "chapter_heads",
                )
            }
            project_version = connection.execute(
                "SELECT concurrency_version FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()[0]
        assert counts == {
            "outlines": 1,
            "outline_revisions": 2,
            "outline_heads": 1,
            "volumes": 2,
            "volume_revisions": 3,
            "volume_heads": 2,
            "chapters": 2,
            "chapter_revisions": 3,
            "chapter_heads": 2,
        }
        assert project_version == 1
