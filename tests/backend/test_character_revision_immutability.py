"""Database-trigger enforcement for immutable Character revisions."""

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.backend.character_repository_support import (
    character_aggregate,
    create_project,
    repository_database,
)

from aiwebnovel.character.persistence.models import CharacterRevisionRecord

pytestmark = pytest.mark.integration

_IMMUTABLE_MESSAGE = "Character revisions are immutable"


def test_all_six_revision_triggers_exist_once_with_stable_names(
    tmp_path: Path,
) -> None:
    with (
        repository_database(tmp_path) as database,
        database.engine.connect() as connection,
    ):
        triggers = list(
            connection.exec_driver_sql(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'trigger' AND name LIKE 'trg_%_revisions_no_%' "
                "ORDER BY name"
            ).scalars()
        )

    assert triggers == [
        "trg_character_revisions_no_delete",
        "trg_character_revisions_no_update",
        "trg_project_revisions_no_delete",
        "trg_project_revisions_no_update",
        "trg_story_bible_revisions_no_delete",
        "trg_story_bible_revisions_no_update",
    ]


def test_direct_sql_update_and_delete_are_rejected_with_safe_errors(
    tmp_path: Path,
) -> None:
    initial = character_aggregate(
        name="private name",
        role="private role",
        profile="private profile",
    )
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        engine = database.engine
        with pytest.raises(IntegrityError) as update_error, engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE character_revisions SET name = ? WHERE id = ?",
                ("replacement", str(initial.current_revision.id)),
            )
        with pytest.raises(IntegrityError) as delete_error, engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM character_revisions WHERE id = ?",
                (str(initial.current_revision.id),),
            )
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT name, role, profile FROM character_revisions WHERE id = ?",
                (str(initial.current_revision.id),),
            ).one()

    assert str(update_error.value.orig) == _IMMUTABLE_MESSAGE
    assert str(delete_error.value.orig) == _IMMUTABLE_MESSAGE
    assert "private" not in str(update_error.value.orig)
    assert "private" not in str(delete_error.value.orig)
    assert row == ("private name", "private role", "private profile")


def test_orm_update_and_delete_are_rejected(tmp_path: Path) -> None:
    initial = character_aggregate()
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        engine = database.engine

        with Session(engine) as session:
            record = session.get(CharacterRevisionRecord, initial.current_revision.id)
            assert record is not None
            record.name = "ORM replacement"
            with pytest.raises(IntegrityError) as update_error:
                session.commit()
            session.rollback()

        with Session(engine) as session:
            record = session.get(CharacterRevisionRecord, initial.current_revision.id)
            assert record is not None
            session.delete(record)
            with pytest.raises(IntegrityError) as delete_error:
                session.commit()
            session.rollback()

    assert str(update_error.value.orig) == _IMMUTABLE_MESSAGE
    assert str(delete_error.value.orig) == _IMMUTABLE_MESSAGE
