"""Consistent current Story Bible aggregate read tests."""

from datetime import UTC
from pathlib import Path

import pytest
from sqlalchemy import event
from tests.backend.story_bible_repository_support import (
    create_project,
    later,
    project_id,
    repository_database,
    story_bible_aggregate,
    story_bible_id,
    story_bible_revision_id,
    table_state,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.story_bible.errors import StoryBibleProjectNotFound
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

pytestmark = pytest.mark.integration


def test_get_missing_returns_none_without_writes(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        assert database.repository.get(story_bible_id(404)) is None
        assert table_state(database.engine)["story_bibles"] == 0


def test_get_for_project_distinguishes_missing_owner_and_no_story_bible(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        with pytest.raises(StoryBibleProjectNotFound):
            database.repository.get_for_project(project_id(404))
        create_project(database)
        assert database.repository.get_for_project(project_id(1)) is None


def test_get_and_get_for_project_restore_same_current_aggregate_with_one_select(
    tmp_path: Path,
) -> None:
    initial = story_bible_aggregate()
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        appended = database.repository.append_revision(
            initial.story_bible.id,
            expected_version=ConcurrencyVersion(1),
            title=StoryBibleTitle("Second"),
            content=StoryBibleContent("Current only"),
            clock=lambda: later(),
            revision_id_factory=lambda: story_bible_revision_id(30_002),
        )

        def capture(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(database.engine, "before_cursor_execute", capture)
        try:
            by_id = database.repository.get(initial.story_bible.id)
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)
        by_project = database.repository.get_for_project(initial.story_bible.project_id)
        state = table_state(database.engine)

    assert by_id == appended
    assert by_project == appended
    assert by_id is not None
    assert by_id.story_bible.created_at.tzinfo is UTC
    assert (
        len(
            [
                statement
                for statement in statements
                if statement.lstrip().upper().startswith("SELECT")
            ]
        )
        == 1
    )
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for statement in statements
    )
    assert state["story_bible_revisions"] == 2
