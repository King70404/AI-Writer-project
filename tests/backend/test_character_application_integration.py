"""Real repository and list-reader integration for Character application use cases."""

from datetime import timedelta
from pathlib import Path

import pytest
from tests.backend.character_repository_support import (
    BASE_TIME,
    character_id,
    character_revision_id,
    create_project,
    repository_database,
)

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)
from aiwebnovel.character.application.queries import (
    GetCharacterQuery,
    ListCharactersForProjectQuery,
)
from aiwebnovel.character.application.services import (
    CharacterCommandService,
    CharacterQueryService,
)
from aiwebnovel.character.persistence.list_reader import SqlAlchemyCharacterListReader

pytestmark = pytest.mark.integration


def test_real_create_list_read_revise_and_latest_read_flow(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        owner = create_project(database)
        reader = SqlAlchemyCharacterListReader(database.session_factory)
        query_service = CharacterQueryService(database.repository, reader)

        first_service = CharacterCommandService(
            database.repository,
            lambda: BASE_TIME,
            lambda: character_id(101),
            lambda: character_revision_id(201),
        )
        first = first_service.create_character(
            CreateCharacterCommand(
                str(owner.project.id),
                "  Shared Name  ",
                "  Protagonist  ",
                "first\r\nprofile",
            )
        )
        second_service = CharacterCommandService(
            database.repository,
            lambda: BASE_TIME + timedelta(seconds=1),
            lambda: character_id(102),
            lambda: character_revision_id(202),
        )
        second = second_service.create_character(
            CreateCharacterCommand(
                str(owner.project.id),
                "Shared Name",
                "Rival",
                "second profile",
            )
        )
        by_id = query_service.get_character(GetCharacterQuery(first.character_id))
        listed = query_service.list_characters_for_project(
            ListCharactersForProjectQuery(str(owner.project.id))
        )

        revision_factory_calls: list[int] = []

        def revision_factory():
            revision_factory_calls.append(1)
            return character_revision_id(203)

        revised = CharacterCommandService(
            database.repository,
            lambda: BASE_TIME + timedelta(seconds=2),
            lambda: character_id(999),
            revision_factory,
        ).revise_character(
            ReviseCharacterCommand(
                first.character_id,
                1,
                "Revised Name",
                "",
                "",
            )
        )
        latest = query_service.get_character(GetCharacterQuery(first.character_id))
        latest_list = query_service.list_characters_for_project(
            ListCharactersForProjectQuery(str(owner.project.id))
        )

        with database.engine.connect() as connection:
            counts = {
                table: connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
                for table in ("characters", "character_revisions", "character_heads")
            }
            first_revisions = connection.exec_driver_sql(
                "SELECT id, revision_number, name, role, profile "
                "FROM character_revisions WHERE character_id = ? "
                "ORDER BY revision_number",
                (first.character_id,),
            ).all()
            head_revision_id = connection.exec_driver_sql(
                "SELECT revision_id FROM character_heads WHERE character_id = ?",
                (first.character_id,),
            ).scalar_one()
            project_state = connection.exec_driver_sql(
                "SELECT concurrency_version FROM projects WHERE id = ?",
                (str(owner.project.id),),
            ).scalar_one()
            project_revision_count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM project_revisions WHERE project_id = ?",
                (str(owner.project.id),),
            ).scalar_one()

    assert first.revision_number == first.concurrency_version == 1
    assert first.name == "Shared Name"
    assert first.role == "Protagonist"
    assert first.profile == "first\nprofile"
    assert second.name == "Shared Name"
    assert by_id == first
    assert {item.character_id for item in listed.items} == {
        first.character_id,
        second.character_id,
    }
    assert all(not hasattr(item, "profile") for item in listed.items)
    assert revised.revision_number == revised.concurrency_version == 2
    assert revised.name == "Revised Name"
    assert revised.role == ""
    assert revised.profile == ""
    assert latest == revised
    assert (
        next(item for item in latest_list.items if item.character_id == first.character_id).name
        == "Revised Name"
    )
    assert revision_factory_calls == [1]
    assert counts == {
        "characters": 2,
        "character_revisions": 3,
        "character_heads": 2,
    }
    assert first_revisions == [
        (
            str(character_revision_id(201)),
            1,
            "Shared Name",
            "Protagonist",
            "first\nprofile",
        ),
        (str(character_revision_id(203)), 2, "Revised Name", "", ""),
    ]
    assert head_revision_id == str(character_revision_id(203))
    assert project_state == 1
    assert project_revision_count == 1
