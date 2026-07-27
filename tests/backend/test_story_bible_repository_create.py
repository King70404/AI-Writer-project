"""Atomic Story Bible aggregate creation tests."""

from pathlib import Path

import pytest
from tests.backend.story_bible_repository_support import (
    create_project,
    repository_database,
    story_bible_aggregate,
    table_state,
)

from aiwebnovel.story_bible.errors import (
    StoryBibleAlreadyExists,
    StoryBibleForProjectAlreadyExists,
    StoryBibleProjectNotFound,
    StoryBibleRepositoryError,
)

pytestmark = pytest.mark.integration


def test_create_atomically_inserts_stable_revision_and_head(tmp_path: Path) -> None:
    initial = story_bible_aggregate(title="Create canary", content="Created once")
    with repository_database(tmp_path) as database:
        create_project(database)
        returned = database.repository.create(initial)
        state = table_state(database.engine)

    assert returned == initial
    assert state == {
        "story_bibles": 1,
        "story_bible_revisions": 1,
        "story_bible_heads": 1,
        "concurrency_version": 1,
        "stable_updated_at": "2026-06-07 08:09:10.000000",
        "head_revision_id": str(initial.current_revision.id),
        "head_updated_at": "2026-06-07 08:09:10.000000",
    }


def test_create_requires_existing_project_and_rolls_back_all_rows(tmp_path: Path) -> None:
    initial = story_bible_aggregate(title="private missing owner")
    with repository_database(tmp_path) as database:
        with pytest.raises(StoryBibleProjectNotFound) as captured:
            database.repository.create(initial)
        state = table_state(database.engine)

    assert captured.value.project_id == initial.story_bible.project_id
    assert "private missing owner" not in str(captured.value)
    assert state["story_bibles"] == 0
    assert state["story_bible_revisions"] == 0
    assert state["story_bible_heads"] == 0


def test_duplicate_story_bible_id_is_specific_and_has_no_changes(tmp_path: Path) -> None:
    initial = story_bible_aggregate(title="private duplicate")
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        before = table_state(database.engine)
        with pytest.raises(StoryBibleAlreadyExists) as captured:
            database.repository.create(initial)
        after = table_state(database.engine)

    assert captured.value.story_bible_id == initial.story_bible.id
    assert "private duplicate" not in str(captured.value)
    assert after == before


def test_project_can_own_at_most_one_story_bible(tmp_path: Path) -> None:
    first = story_bible_aggregate(1)
    second = story_bible_aggregate(2, project_value=1)
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(first)
        before = table_state(database.engine)
        with pytest.raises(StoryBibleForProjectAlreadyExists) as captured:
            database.repository.create(second)
        after = table_state(database.engine)

    assert captured.value.project_id == first.story_bible.project_id
    assert after == before


@pytest.mark.parametrize(
    ("table", "trigger"),
    [
        ("story_bible_revisions", "test_fail_story_bible_revision_insert"),
        ("story_bible_heads", "test_fail_story_bible_head_insert"),
    ],
)
def test_revision_or_head_insert_failure_rolls_back_entire_create(
    tmp_path: Path,
    table: str,
    trigger: str,
) -> None:
    initial = story_bible_aggregate()
    with repository_database(tmp_path) as database:
        create_project(database)
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON {table} BEGIN "
                "SELECT RAISE(ABORT, 'controlled insert failure'); END"
            )
        try:
            with pytest.raises(StoryBibleRepositoryError) as captured:
                database.repository.create(initial)
            state = table_state(database.engine)
        finally:
            with database.engine.begin() as connection:
                connection.exec_driver_sql(f"DROP TRIGGER {trigger}")

    assert str(captured.value) == "The Story Bible persistence operation could not be completed."
    assert state["story_bibles"] == 0
    assert state["story_bible_revisions"] == 0
    assert state["story_bible_heads"] == 0


def test_duplicate_revision_id_rolls_back_new_stable_object(tmp_path: Path) -> None:
    existing = story_bible_aggregate(1, revision_value=90)
    colliding = story_bible_aggregate(2, revision_value=90)
    with repository_database(tmp_path) as database:
        create_project(database)
        create_project(database, 2)
        database.repository.create(existing)
        before = table_state(database.engine)
        with pytest.raises(StoryBibleRepositoryError):
            database.repository.create(colliding)
        after = table_state(database.engine)

    assert after == before
