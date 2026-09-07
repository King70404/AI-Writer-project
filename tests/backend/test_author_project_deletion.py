"""Author deletion keeps immutable data while hiding normal child workflows."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.character_repository_support import repository_database
from tests.backend.factories import create_test_app
from tests.backend.project_api_support import issue_write_headers

pytestmark = pytest.mark.integration


def test_delete_hides_project_and_children_without_rewriting_revisions(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        app = create_test_app(
            data_root=tmp_path / "http",
            database_url=str(database.engine.url),
        )
        with TestClient(app) as client:
            headers = issue_write_headers(client)
            created = client.post(
                "/api/v1/projects",
                headers=headers,
                json={"title": "Author deletion regression", "description": "Original description"},
            )
            assert created.status_code == 201
            project = created.json()["project_id"]
            revision = created.json()["current_revision_id"]
            bible = client.post(
                f"/api/v1/projects/{project}/story-bible",
                headers=headers,
                json={"title": "Setting", "content": "Original setting"},
            )
            assert bible.status_code == 201
            character = client.post(
                f"/api/v1/projects/{project}/characters",
                headers=headers,
                json={
                    "name": "Original name",
                    "role": "Protagonist",
                    "profile": "Original profile",
                },
            )
            assert character.status_code == 201
            with closing(sqlite3.connect(database.engine.url.database)) as connection:
                before = {
                    table: connection.execute(f"SELECT * FROM {table}").fetchall()
                    for table in (
                        "story_bible_revisions",
                        "character_revisions",
                        "project_revisions",
                    )
                }
            url = f"/api/v1/projects/{project}/delete"
            assert client.post(url, headers={**headers, "If-Match": '"2"'}).status_code == 412
            assert client.get(f"/api/v1/projects/{project}").status_code == 200
            deleted = client.post(url, headers={**headers, "If-Match": created.headers["etag"]})
            assert deleted.status_code == 200
            assert deleted.json() == {"deleted": True}
            for path in (
                f"/api/v1/projects/{project}",
                f"/api/v1/projects/{project}/revisions",
                f"/api/v1/projects/{project}/revisions/1",
                f"/api/v1/projects/{project}/story-bible",
                f"/api/v1/projects/{project}/characters",
                f"/api/v1/story-bibles/{bible.json()['story_bible_id']}",
                f"/api/v1/characters/{character.json()['character_id']}",
            ):
                assert client.get(path).status_code == 404, path
            listing = client.get("/api/v1/projects")
            assert listing.status_code == 200
            assert project not in {item["project_id"] for item in listing.json()["items"]}
            assert client.post(url, headers={**headers, "If-Match": '"2"'}).status_code == 404
            with closing(sqlite3.connect(database.engine.url.database)) as connection:
                for table in ("story_bible_revisions", "character_revisions"):
                    assert connection.execute(f"SELECT * FROM {table}").fetchall() == before[table]
                assert (
                    connection.execute(
                        "SELECT * FROM project_revisions WHERE id = ?",
                        (revision,),
                    ).fetchall()
                    == before["project_revisions"]
                )
                assert connection.execute("SELECT COUNT(*) FROM project_revisions").fetchone() == (
                    2,
                )
                assert connection.execute("SELECT COUNT(*) FROM projects").fetchone() == (1,)


def test_delete_requires_csrf_and_etag_and_reserved_prefix_is_not_author_input(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        app = create_test_app(data_root=tmp_path / "http", database_url=str(database.engine.url))
        with TestClient(app) as client:
            headers = issue_write_headers(client)
            created = client.post("/api/v1/projects", headers=headers, json={"title": "Keep me"})
            assert created.status_code == 201
            project = created.json()["project_id"]
            url = f"/api/v1/projects/{project}/delete"
            assert client.post(url, headers={"If-Match": '"1"'}).status_code == 403
            assert client.post(url, headers=headers).status_code == 428
            assert client.post(url, headers={**headers, "If-Match": "1"}).status_code == 400
            assert client.get(f"/api/v1/projects/{project}").json() == created.json()
            rejected = client.post(
                "/api/v1/projects",
                headers=headers,
                json={"title": f"__AIWEBNOVEL_DELETED__:{project}"},
            )
            assert rejected.status_code == 422
            ordinary = client.post(
                "/api/v1/projects",
                headers=headers,
                json={"title": f"xxAIWEBNOVELxDELETEDxx:{project}"},
            )
            assert ordinary.status_code == 201
            listing = client.get("/api/v1/projects").json()["items"]
            assert {item["project_id"] for item in listing} == {
                project,
                ordinary.json()["project_id"],
            }
