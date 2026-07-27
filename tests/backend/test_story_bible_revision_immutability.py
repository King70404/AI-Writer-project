"""Database-trigger enforcement for immutable Story Bible revisions."""

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.backend.story_bible_repository_support import (
    create_project,
    repository_database,
    story_bible_aggregate,
)

from aiwebnovel.story_bible.persistence.models import StoryBibleRevisionRecord

pytestmark = pytest.mark.integration

_IMMUTABLE_MESSAGE = "Story Bible revisions are immutable"


def test_revision_triggers_exist_once_with_stable_names(tmp_path: Path) -> None:
    with (
        repository_database(tmp_path) as database,
        database.engine.connect() as connection,
    ):
        triggers = list(
            connection.exec_driver_sql(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'trigger' AND tbl_name = 'story_bible_revisions' "
                "ORDER BY name"
            ).scalars()
        )

    assert triggers == [
        "trg_story_bible_revisions_no_delete",
        "trg_story_bible_revisions_no_update",
    ]


def test_direct_sql_update_and_delete_are_rejected_with_safe_errors(
    tmp_path: Path,
) -> None:
    initial = story_bible_aggregate(title="private title", content="private content")
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        engine = database.engine
        with pytest.raises(IntegrityError) as update_error, engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE story_bible_revisions SET title = ? WHERE id = ?",
                ("replacement", str(initial.current_revision.id)),
            )
        with pytest.raises(IntegrityError) as delete_error, engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM story_bible_revisions WHERE id = ?",
                (str(initial.current_revision.id),),
            )
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT title, content FROM story_bible_revisions WHERE id = ?",
                (str(initial.current_revision.id),),
            ).one()

    assert str(update_error.value.orig) == _IMMUTABLE_MESSAGE
    assert str(delete_error.value.orig) == _IMMUTABLE_MESSAGE
    assert "private" not in str(update_error.value.orig)
    assert "private" not in str(delete_error.value.orig)
    assert row == ("private title", "private content")


def test_orm_update_and_delete_are_rejected_without_hiding_failure(
    tmp_path: Path,
) -> None:
    initial = story_bible_aggregate()
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        engine = database.engine

        with Session(engine) as session:
            record = session.get(StoryBibleRevisionRecord, initial.current_revision.id)
            assert record is not None
            record.title = "ORM replacement"
            with pytest.raises(IntegrityError) as update_error:
                session.commit()
            session.rollback()

        with Session(engine) as session:
            record = session.get(StoryBibleRevisionRecord, initial.current_revision.id)
            assert record is not None
            session.delete(record)
            with pytest.raises(IntegrityError) as delete_error:
                session.commit()
            session.rollback()

        with engine.connect() as connection:
            count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM story_bible_revisions"
            ).scalar_one()

    assert str(update_error.value.orig) == _IMMUTABLE_MESSAGE
    assert str(delete_error.value.orig) == _IMMUTABLE_MESSAGE
    assert count == 1
