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
            history_paths: list[str] = []
            for child, child_path, replacement in (
                (
                    bible,
                    f"/api/v1/story-bibles/{bible.json()['story_bible_id']}",
                    {"title": "Updated setting", "content": "Updated setting body"},
                ),
                (
                    character,
                    f"/api/v1/characters/{character.json()['character_id']}",
                    {
                        "name": "Updated name",
                        "role": "Protagonist",
                        "profile": "Updated profile",
                    },
                ),
            ):
                revised = client.put(
                    child_path,
                    headers={**headers, "If-Match": child.headers["etag"]},
                    json=replacement,
                )
                assert revised.status_code == 200
                history = client.get(f"{child_path}/revisions?limit=1")
                assert history.status_code == 200
                cursor = history.json()["next_cursor"]
                assert cursor is not None
                paths = (
                    f"{child_path}/revisions",
                    f"{child_path}/revisions?limit=1&cursor={cursor}",
                    f"{child_path}/revisions/1",
                    f"{child_path}/revisions/2",
                )
                for path in paths:
                    assert client.get(path).status_code == 200, path
                history_paths.extend(paths)
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
            blocked_paths = (
                f"/api/v1/projects/{project}",
                f"/api/v1/projects/{project}/revisions",
                f"/api/v1/projects/{project}/revisions/1",
                f"/api/v1/projects/{project}/story-bible",
                f"/api/v1/projects/{project}/characters",
                f"/api/v1/story-bibles/{bible.json()['story_bible_id']}",
                f"/api/v1/characters/{character.json()['character_id']}",
                *history_paths,
            )
            responses = {path: client.get(path) for path in blocked_paths}
            assert {path: response.status_code for path, response in responses.items()} == {
                path: 404 for path in blocked_paths
            }
            for path in history_paths:
                response = responses[path]
                expected_code = (
                    "CHARACTER_NOT_FOUND" if "/characters/" in path else "STORY_BIBLE_NOT_FOUND"
                )
                assert response.json()["error"]["code"] == expected_code
                assert "ETag" not in response.headers
                assert all(
                    text not in response.text
                    for text in (
                        "Original name",
                        "Original profile",
                        "Original setting",
                        "Updated name",
                        "Updated profile",
                        "Updated setting",
                    )
                )
            listing = client.get("/api/v1/projects")
            assert listing.status_code == 200
            assert project not in {item["project_id"] for item in listing.json()["items"]}
            assert client.post(url, headers={**headers, "If-Match": '"2"'}).status_code == 404
            with closing(sqlite3.connect(database.engine.url.database)) as connection:
                for table, rows in before.items():
                    for row in rows:
                        assert (
                            connection.execute(
                                f"SELECT * FROM {table} WHERE id = ?", (row[0],)
                            ).fetchone()
                            == row
                        )
                    expected_count = len(rows) + (1 if table == "project_revisions" else 0)
                    assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (
                        expected_count,
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
