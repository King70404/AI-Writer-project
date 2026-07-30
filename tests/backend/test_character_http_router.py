"""Four Character route contracts over recording application services."""

from pathlib import Path

from fastapi.testclient import TestClient
from tests.backend.character_http_support import (
    CHARACTER_ID,
    PROJECT_ID,
    isolated_app,
    issue_write_headers,
    list_page,
    snapshot,
)

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)
from aiwebnovel.character.application.queries import (
    GetCharacterQuery,
    ListCharactersForProjectQuery,
)
from aiwebnovel.character.web.dependencies import (
    get_character_command_service,
    get_character_query_service,
)


class RecordingCommandService:
    def __init__(self) -> None:
        self.create_commands: list[CreateCharacterCommand] = []
        self.revise_commands: list[ReviseCharacterCommand] = []

    def create_character(self, command: CreateCharacterCommand):
        self.create_commands.append(command)
        return snapshot(name=command.name.strip(), role=command.role, profile=command.profile)

    def revise_character(self, command: ReviseCharacterCommand):
        self.revise_commands.append(command)
        return snapshot(
            version=2,
            name=command.name,
            role=command.role,
            profile=command.profile,
        )


class RecordingQueryService:
    def __init__(self) -> None:
        self.get_queries: list[GetCharacterQuery] = []
        self.list_queries: list[ListCharactersForProjectQuery] = []

    def get_character(self, query: GetCharacterQuery):
        self.get_queries.append(query)
        return snapshot()

    def list_characters_for_project(self, query: ListCharactersForProjectQuery):
        self.list_queries.append(query)
        return list_page()


def _app_with_services(tmp_path: Path):
    app = isolated_app(tmp_path)
    commands = RecordingCommandService()
    queries = RecordingQueryService()
    app.dependency_overrides[get_character_command_service] = lambda: commands
    app.dependency_overrides[get_character_query_service] = lambda: queries
    return app, commands, queries


def test_post_creates_once_with_location_etag_and_duplicate_names_allowed(
    tmp_path: Path,
) -> None:
    app, commands, queries = _app_with_services(tmp_path)
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        first = client.post(
            f"/api/v1/projects/{PROJECT_ID}/characters",
            headers=headers,
            json={"name": " Character "},
        )
        second = client.post(
            f"/api/v1/projects/{PROJECT_ID}/characters",
            headers=headers,
            json={"name": " Character "},
        )
    assert first.status_code == second.status_code == 201
    assert first.headers["ETag"] == '"1"'
    assert first.headers["Location"] == f"/api/v1/characters/{CHARACTER_ID}"
    assert first.headers["Cache-Control"] == "no-store"
    assert commands.create_commands == [
        CreateCharacterCommand(PROJECT_ID, " Character ", "", ""),
        CreateCharacterCommand(PROJECT_ID, " Character ", "", ""),
    ]
    assert queries.get_queries == queries.list_queries == []


def test_get_and_list_are_read_only_profile_safe_and_project_bound(
    tmp_path: Path,
) -> None:
    app, commands, queries = _app_with_services(tmp_path)
    with TestClient(app) as client:
        read = client.get(f"/api/v1/characters/{CHARACTER_ID}")
        listed = client.get(f"/api/v1/projects/{PROJECT_ID}/characters?limit=20")
    assert read.status_code == listed.status_code == 200
    assert read.json()["profile"] == "Initial profile"
    assert read.headers["ETag"] == '"1"'
    assert listed.headers["Cache-Control"] == "no-store"
    assert "ETag" not in listed.headers
    assert "profile" not in listed.json()["items"][0]
    assert "total" not in listed.json()
    assert queries.get_queries == [GetCharacterQuery(CHARACTER_ID)]
    assert len(queries.list_queries) == 1
    assert queries.list_queries[0].project_id == PROJECT_ID
    assert commands.create_commands == commands.revise_commands == []


def test_put_is_one_complete_replacement_without_pre_read(tmp_path: Path) -> None:
    app, commands, queries = _app_with_services(tmp_path)
    with TestClient(app) as client:
        response = client.put(
            f"/api/v1/characters/{CHARACTER_ID}",
            headers={**issue_write_headers(client), "If-Match": '"1"'},
            json={"name": "Replacement", "role": "", "profile": ""},
        )
    assert response.status_code == 200
    assert response.headers["ETag"] == '"2"'
    assert response.json()["profile"] == ""
    assert commands.revise_commands == [
        ReviseCharacterCommand(CHARACTER_ID, 1, "Replacement", "", "")
    ]
    assert queries.get_queries == queries.list_queries == []


def test_invalid_ids_and_list_parameters_do_not_call_services(tmp_path: Path) -> None:
    app, commands, queries = _app_with_services(tmp_path)
    with TestClient(app) as client:
        responses = (
            client.get("/api/v1/characters/not-an-id"),
            client.get(f"/api/v1/projects/{PROJECT_ID}/characters?limit=true"),
            client.get(f"/api/v1/projects/{PROJECT_ID}/characters?unknown=1"),
        )
    assert [response.status_code for response in responses] == [422, 422, 422]
    assert commands.create_commands == commands.revise_commands == []
    assert queries.get_queries == queries.list_queries == []
