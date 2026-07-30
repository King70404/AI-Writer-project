"""Real migrated Character HTTP create/list/read/revise flow."""

import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.character_http_support import issue_write_headers
from tests.backend.character_repository_support import (
    BASE_TIME,
    character_id,
    character_revision_id,
)
from tests.backend.factories import create_test_settings
from tests.backend.project_api_support import create_test_app_from_settings
from tests.backend.test_character_migration import migrated_character_database_context

from aiwebnovel.character.application.commands import CreateCharacterCommand
from aiwebnovel.character.application.services import (
    CharacterCommandService,
    CharacterQueryService,
)
from aiwebnovel.character.persistence.list_reader import SqlAlchemyCharacterListReader
from aiwebnovel.character.persistence.repository import SqlAlchemyCharacterRepository
from aiwebnovel.character.web.dependencies import (
    get_character_command_service,
    get_character_query_service,
)

pytestmark = pytest.mark.integration


def test_real_http_create_two_same_name_list_read_and_revise(tmp_path: Path) -> None:
    with migrated_character_database_context(tmp_path) as database:
        settings = create_test_settings(
            data_root=(tmp_path / "character-http-storage").resolve(),
            database_url=str(
                URL.create("sqlite+pysqlite", database=database.path.resolve().as_posix())
            ),
        )
        app = create_test_app_from_settings(settings)
        with TestClient(app) as client:
            headers = issue_write_headers(client)
            project = client.post(
                "/api/v1/projects",
                headers=headers,
                json={"title": "Character owner"},
            )
            project_id = project.json()["project_id"]
            repository = SqlAlchemyCharacterRepository(app.state.database_session_factory)
            reader = SqlAlchemyCharacterListReader(app.state.database_session_factory)
            ids = iter((character_id(101), character_id(102)))
            revisions = iter(
                (
                    character_revision_id(201),
                    character_revision_id(202),
                    character_revision_id(203),
                )
            )
            times = iter(
                (
                    BASE_TIME,
                    BASE_TIME + timedelta(seconds=1),
                    BASE_TIME + timedelta(seconds=2),
                )
            )
            command_service = CharacterCommandService(
                repository,
                lambda: next(times),
                lambda: next(ids),
                lambda: next(revisions),
            )
            query_service = CharacterQueryService(repository, reader)
            app.dependency_overrides[get_character_command_service] = lambda: command_service
            app.dependency_overrides[get_character_query_service] = lambda: query_service

            first = client.post(
                f"/api/v1/projects/{project_id}/characters",
                headers=headers,
                json={"name": "Shared", "role": "Lead", "profile": "first\r\nprofile"},
            )
            second = client.post(
                f"/api/v1/projects/{project_id}/characters",
                headers=headers,
                json={"name": "Shared", "role": "Rival", "profile": "second"},
            )
            listed = client.get(f"/api/v1/projects/{project_id}/characters")
            read = client.get(f"/api/v1/characters/{first.json()['character_id']}")
            revised = client.put(
                f"/api/v1/characters/{first.json()['character_id']}",
                headers={**headers, "If-Match": first.headers["ETag"]},
                json={"name": "Revised", "role": "", "profile": ""},
            )
            latest = client.get(f"/api/v1/characters/{first.json()['character_id']}")

        assert first.status_code == second.status_code == 201
        assert first.json()["profile"] == "first\nprofile"
        assert len(listed.json()["items"]) == 2
        assert {item["name"] for item in listed.json()["items"]} == {"Shared"}
        assert all("profile" not in item for item in listed.json()["items"])
        assert read.json() == first.json()
        assert revised.status_code == 200
        assert revised.headers["ETag"] == '"2"'
        assert revised.json()["name"] == "Revised"
        assert revised.json()["role"] == revised.json()["profile"] == ""
        assert latest.json() == revised.json()
        with closing(sqlite3.connect(database.path)) as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("characters", "character_revisions", "character_heads")
            }
            project_version = connection.execute(
                "SELECT concurrency_version FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()[0]
        assert counts == {
            "characters": 2,
            "character_revisions": 3,
            "character_heads": 2,
        }
        assert project_version == 1


def test_real_http_paginates_twenty_three_characters_without_gaps(
    tmp_path: Path,
) -> None:
    with migrated_character_database_context(tmp_path) as database:
        app = create_test_app_from_settings(
            create_test_settings(
                data_root=(tmp_path / "character-http-pagination-storage").resolve(),
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
            first_project = client.post(
                "/api/v1/projects",
                headers=headers,
                json={"title": "First owner"},
            ).json()["project_id"]
            second_project = client.post(
                "/api/v1/projects",
                headers=headers,
                json={"title": "Second owner"},
            ).json()["project_id"]
            repository = SqlAlchemyCharacterRepository(app.state.database_session_factory)
            for index in range(23):
                CharacterCommandService(
                    repository,
                    lambda index=index: BASE_TIME + timedelta(seconds=index // 3),
                    lambda index=index: character_id(1_000 + index),
                    lambda index=index: character_revision_id(2_000 + index),
                ).create_character(
                    CreateCharacterCommand(
                        first_project,
                        f"Character {index:02d}",
                        "",
                        f"profile {index}",
                    )
                )

            pages = []
            cursor = None
            while True:
                suffix = "" if cursor is None else f"?cursor={cursor}"
                page = client.get(f"/api/v1/projects/{first_project}/characters{suffix}").json()
                pages.append(page)
                if not page["has_more"]:
                    break
                cursor = page["next_cursor"]
                if len(pages) == 1:
                    CharacterCommandService(
                        repository,
                        lambda: BASE_TIME + timedelta(days=1),
                        lambda: character_id(9_999),
                        lambda: character_revision_id(9_999),
                    ).create_character(
                        CreateCharacterCommand(
                            first_project,
                            "Newer Character",
                            "",
                            "must not enter an old cursor continuation",
                        )
                    )
            wrong_project = client.get(
                f"/api/v1/projects/{second_project}/characters?cursor={pages[0]['next_cursor']}"
            )

        items = [item for page in pages for item in page["items"]]
        assert [len(page["items"]) for page in pages] == [20, 3]
        assert len({item["character_id"] for item in items}) == 23
        assert [item["name"] for item in items] == [
            f"Character {index:02d}" for index in reversed(range(23))
        ]
        assert "Newer Character" not in {item["name"] for item in items}
        assert all("profile" not in item for item in items)
        assert wrong_project.status_code == 400
        assert wrong_project.json()["error"]["code"] == "INVALID_CHARACTER_CURSOR"
