"""Atomic Character aggregate creation tests."""

from pathlib import Path

import pytest
from tests.backend.character_repository_support import (
    character_aggregate,
    create_project,
    repository_database,
    table_state,
)

from aiwebnovel.character.errors import (
    CharacterAlreadyExists,
    CharacterProjectNotFound,
    CharacterRepositoryError,
)

pytestmark = pytest.mark.integration


def test_create_atomically_inserts_stable_revision_and_head(tmp_path: Path) -> None:
    initial = character_aggregate(
        name="Create canary",
        role="Lead",
        profile="Created once",
    )
    with repository_database(tmp_path) as database:
        create_project(database)
        returned = database.repository.create(initial)
        state = table_state(database.engine)

    assert returned == initial
    assert state == {
        "characters": 1,
        "character_revisions": 1,
        "character_heads": 1,
        "concurrency_version": 1,
        "stable_updated_at": "2026-07-29 08:09:10.000000",
        "head_revision_id": str(initial.current_revision.id),
        "head_updated_at": "2026-07-29 08:09:10.000000",
    }


def test_create_requires_existing_project_and_rolls_back_all_rows(
    tmp_path: Path,
) -> None:
    initial = character_aggregate(name="CHARACTER_PERSISTENCE_SECRET_CANARY")
    with repository_database(tmp_path) as database:
        with pytest.raises(CharacterProjectNotFound) as captured:
            database.repository.create(initial)
        state = table_state(database.engine)

    assert captured.value.project_id == initial.character.project_id
    assert "CANARY" not in str(captured.value)
    assert state["characters"] == 0
    assert state["character_revisions"] == 0
    assert state["character_heads"] == 0


def test_duplicate_character_id_is_specific_and_has_no_changes(tmp_path: Path) -> None:
    initial = character_aggregate(name="private duplicate")
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        before = table_state(database.engine)
        with pytest.raises(CharacterAlreadyExists) as captured:
            database.repository.create(initial)
        after = table_state(database.engine)

    assert captured.value.character_id == initial.character.id
    assert "private duplicate" not in str(captured.value)
    assert after == before


def test_project_can_own_multiple_characters_with_the_same_name(tmp_path: Path) -> None:
    first = character_aggregate(1, name="Same Name")
    second = character_aggregate(2, project_value=1, name="Same Name")
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(first)
        database.repository.create(second)
        with database.engine.connect() as connection:
            count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM characters WHERE project_id = ?",
                (str(first.character.project_id),),
            ).scalar_one()

    assert count == 2


@pytest.mark.parametrize(
    ("table", "trigger"),
    [
        ("character_revisions", "test_fail_character_revision_insert"),
        ("character_heads", "test_fail_character_head_insert"),
    ],
)
def test_late_insert_failure_rolls_back_entire_create(
    tmp_path: Path,
    table: str,
    trigger: str,
) -> None:
    initial = character_aggregate()
    with repository_database(tmp_path) as database:
        create_project(database)
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON {table} BEGIN "
                "SELECT RAISE(ABORT, 'controlled insert failure'); END"
            )
        try:
            with pytest.raises(CharacterRepositoryError) as captured:
                database.repository.create(initial)
            state = table_state(database.engine)
        finally:
            with database.engine.begin() as connection:
                connection.exec_driver_sql(f"DROP TRIGGER {trigger}")

    assert str(captured.value) == ("The Character persistence operation could not be completed.")
    assert state["characters"] == 0
    assert state["character_revisions"] == 0
    assert state["character_heads"] == 0


def test_duplicate_revision_id_rolls_back_new_stable_object(tmp_path: Path) -> None:
    existing = character_aggregate(1, revision_value=90)
    colliding = character_aggregate(2, project_value=2, revision_value=90)
    with repository_database(tmp_path) as database:
        create_project(database)
        create_project(database, 2)
        database.repository.create(existing)
        before = table_state(database.engine)
        with pytest.raises(CharacterRepositoryError):
            database.repository.create(colliding)
        after = table_state(database.engine)

    assert after == before
