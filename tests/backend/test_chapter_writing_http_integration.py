"""Real Chapter manuscript HTTP flow through application and SQLite."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.character_http_support import issue_write_headers
from tests.backend.factories import create_test_settings
from tests.backend.novel_structure_repository_support import chapter_id as deterministic_chapter_id
from tests.backend.project_api_support import create_test_app_from_settings
from tests.backend.test_novel_structure_migration import (
    migrated_novel_structure_database_context,
)

pytestmark = pytest.mark.integration


def test_chapter_content_http_round_trip_concurrency_and_revision_integrity(
    tmp_path: Path,
) -> None:
    with migrated_novel_structure_database_context(tmp_path) as database:
        app = create_test_app_from_settings(
            create_test_settings(
                data_root=(tmp_path / "chapter-writing-http-storage").resolve(),
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
                json={"title": "Writing owner"},
            )
            project_id = project.json()["project_id"]
            volume = client.post(
                f"/api/v1/projects/{project_id}/volumes",
                headers=headers,
                json={"title": "Volume", "summary": "volume summary", "position": 1},
            )
            volume_id = volume.json()["volume_id"]
            created = client.post(
                f"/api/v1/projects/{project_id}/volumes/{volume_id}/chapters",
                headers=headers,
                json={"title": "Chapter A", "summary": "chapter summary", "position": 2},
            )
            chapter_id = created.json()["chapter_id"]

            initial = client.get(f"/api/v1/chapters/{chapter_id}/content")
            structural = client.get(f"/api/v1/chapters/{chapter_id}")
            missing_precondition = client.put(
                f"/api/v1/chapters/{chapter_id}/content",
                headers=headers,
                json={"content": "draft"},
            )
            malformed_precondition = client.put(
                f"/api/v1/chapters/{chapter_id}/content",
                headers={**headers, "If-Match": "1"},
                json={"content": "draft"},
            )
            written = client.put(
                f"/api/v1/chapters/{chapter_id}/content",
                headers={**headers, "If-Match": initial.headers["ETag"]},
                json={"content": "第一稿\r\n第二行"},
            )
            reread = client.get(f"/api/v1/chapters/{chapter_id}/content")
            stale = client.put(
                f"/api/v1/chapters/{chapter_id}/content",
                headers={**headers, "If-Match": initial.headers["ETag"]},
                json={"content": "must not persist"},
            )
            structure_update = client.put(
                f"/api/v1/chapters/{chapter_id}",
                headers={**headers, "If-Match": written.headers["ETag"]},
                json={"title": "Chapter B", "summary": "new summary", "position": 3},
            )
            after_structure = client.get(f"/api/v1/chapters/{chapter_id}/content")
            rewritten = client.put(
                f"/api/v1/chapters/{chapter_id}/content",
                headers={**headers, "If-Match": structure_update.headers["ETag"]},
                json={"content": "第二稿"},
            )
            final_structure = client.get(f"/api/v1/chapters/{chapter_id}")
            missing_id = str(deterministic_chapter_id(99_999))
            missing = client.get(f"/api/v1/chapters/{missing_id}/content")
            invalid_id = client.get("/api/v1/chapters/not-a-chapter/content")
            invalid_content = client.put(
                f"/api/v1/chapters/{chapter_id}/content",
                headers={**headers, "If-Match": rewritten.headers["ETag"]},
                json={"content": "STORY_CONTENT_SECRET_CANARY\u0000"},
            )
            forbidden_post = client.post(
                f"/api/v1/chapters/{chapter_id}/content",
                headers=headers,
                json={"content": "not supported"},
            )

        assert project.status_code == volume.status_code == created.status_code == 201
        assert initial.status_code == 200
        assert initial.json()["content"] == ""
        assert initial.headers["ETag"] == '"1"'
        assert initial.headers["Cache-Control"] == "no-store"
        assert "content" not in created.json()
        assert "content" not in structural.json()
        assert missing_precondition.status_code == 428
        assert malformed_precondition.status_code == 400
        assert written.status_code == 200
        assert written.headers["ETag"] == '"2"'
        assert written.json()["content"] == "第一稿\n第二行"
        assert written.json()["revision_number"] == 2
        assert reread.json() == written.json()
        assert reread.headers["ETag"] == written.headers["ETag"]
        assert stale.status_code == 412
        assert stale.json()["error"]["details"] == {
            "expected_version": 1,
            "actual_version": 2,
        }
        assert structure_update.status_code == 200
        assert structure_update.headers["ETag"] == '"3"'
        assert "content" not in structure_update.json()
        assert after_structure.json()["content"] == "第一稿\n第二行"
        assert after_structure.json()["revision_number"] == 3
        assert rewritten.status_code == 200
        assert rewritten.headers["ETag"] == '"4"'
        assert rewritten.json()["content"] == "第二稿"
        assert final_structure.json()["title"] == "Chapter B"
        assert final_structure.json()["summary"] == "new summary"
        assert final_structure.json()["position"] == 3
        assert missing.status_code == 404
        assert invalid_id.status_code == 422
        assert invalid_content.status_code == 422
        assert "STORY_CONTENT_SECRET_CANARY" not in invalid_content.text
        assert forbidden_post.status_code == 405

        with closing(sqlite3.connect(database.path)) as connection:
            revisions = connection.execute(
                "SELECT revision_number, title, summary, position, content "
                "FROM chapter_revisions WHERE chapter_id = ? ORDER BY revision_number",
                (chapter_id,),
            ).fetchall()
            head_revision = connection.execute(
                "SELECT revision_id FROM chapter_heads WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()[0]
        assert revisions == [
            (1, "Chapter A", "chapter summary", 2, ""),
            (2, "Chapter A", "chapter summary", 2, "第一稿\n第二行"),
            (3, "Chapter B", "new summary", 3, "第一稿\n第二行"),
            (4, "Chapter B", "new summary", 3, "第二稿"),
        ]
        assert head_revision == rewritten.json()["current_revision_id"]
