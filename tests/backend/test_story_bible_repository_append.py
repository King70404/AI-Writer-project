"""Atomic immutable Story Bible revision append tests."""

from pathlib import Path

import pytest
from sqlalchemy import event
from tests.backend.story_bible_repository_support import (
    create_project,
    later,
    repository_database,
    story_bible_aggregate,
    story_bible_id,
    story_bible_revision_id,
    table_state,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.story_bible.errors import (
    StoryBibleNotFound,
    StoryBibleRepositoryError,
)
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

pytestmark = pytest.mark.integration


def test_append_inserts_complete_revision_then_moves_stable_and_head_with_cas(
    tmp_path: Path,
) -> None:
    initial = story_bible_aggregate()
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)

        def capture_write(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE")):
                statements.append(" ".join(statement.split()))

        event.listen(database.engine, "before_cursor_execute", capture_write)
        try:
            appended = database.repository.append_revision(
                initial.story_bible.id,
                expected_version=ConcurrencyVersion(1),
                title=StoryBibleTitle("Second revision"),
                content=StoryBibleContent("A complete immutable snapshot"),
                clock=lambda: later(),
                revision_id_factory=lambda: story_bible_revision_id(30_002),
            )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture_write)

        restored = database.repository.get(initial.story_bible.id)
        state = table_state(database.engine)
        with database.engine.connect() as connection:
            history = connection.exec_driver_sql(
                "SELECT id, revision_number, title, content "
                "FROM story_bible_revisions WHERE story_bible_id = ? "
                "ORDER BY revision_number",
                (str(initial.story_bible.id),),
            ).all()

    assert restored == appended
    assert int(appended.story_bible.concurrency_version) == 2
    assert int(appended.current_revision.revision_number) == 2
    assert appended.head.revision_id == appended.current_revision.id
    assert state["story_bibles"] == 1
    assert state["story_bible_revisions"] == 2
    assert state["story_bible_heads"] == 1
    assert state["concurrency_version"] == 2
    assert state["head_revision_id"] == str(story_bible_revision_id(30_002))
    assert history == [
        (
            str(initial.current_revision.id),
            1,
            "Story Bible",
            "Initial setting",
        ),
        (
            str(story_bible_revision_id(30_002)),
            2,
            "Second revision",
            "A complete immutable snapshot",
        ),
    ]
    assert len(statements) == 3
    stable_cas = next(
        statement for statement in statements if statement.startswith("UPDATE story_bibles")
    )
    head_cas = next(
        statement for statement in statements if statement.startswith("UPDATE story_bible_heads")
    )
    assert "story_bibles.id = ?" in stable_cas
    assert "story_bibles.concurrency_version = ?" in stable_cas
    assert "story_bible_heads.story_bible_id = ?" in head_cas
    assert "story_bible_heads.revision_id = ?" in head_cas


def test_missing_story_bible_rejects_before_clock_and_id_factory(tmp_path: Path) -> None:
    calls = {"clock": 0, "id": 0}

    def clock():
        calls["clock"] += 1
        return later()

    def identifier_factory():
        calls["id"] += 1
        return story_bible_revision_id(999)

    with repository_database(tmp_path) as database, pytest.raises(StoryBibleNotFound):
        database.repository.append_revision(
            story_bible_id(404),
            expected_version=ConcurrencyVersion(1),
            title=StoryBibleTitle("Missing"),
            content=StoryBibleContent(),
            clock=clock,
            revision_id_factory=identifier_factory,
        )

    assert calls == {"clock": 0, "id": 0}


def test_stale_append_has_no_clock_id_or_database_side_effect(tmp_path: Path) -> None:
    initial = story_bible_aggregate()
    calls = {"clock": 0, "id": 0}

    def clock():
        calls["clock"] += 1
        return later(2)

    def identifier_factory():
        calls["id"] += 1
        return story_bible_revision_id(30_003)

    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        database.repository.append_revision(
            initial.story_bible.id,
            expected_version=ConcurrencyVersion(1),
            title=StoryBibleTitle("Second"),
            content=StoryBibleContent(),
            clock=lambda: later(),
            revision_id_factory=lambda: story_bible_revision_id(30_002),
        )
        before = table_state(database.engine)
        with pytest.raises(ConcurrencyConflict) as captured:
            database.repository.append_revision(
                initial.story_bible.id,
                expected_version=ConcurrencyVersion(1),
                title=StoryBibleTitle("private stale title"),
                content=StoryBibleContent("private stale content"),
                clock=clock,
                revision_id_factory=identifier_factory,
            )
        after = table_state(database.engine)

    assert captured.value.expected_version == 1
    assert captured.value.actual_version == 2
    assert "private" not in str(captured.value)
    assert calls == {"clock": 0, "id": 0}
    assert after == before


def test_duplicate_revision_id_rolls_back_revision_stable_and_head(tmp_path: Path) -> None:
    initial = story_bible_aggregate()
    other = story_bible_aggregate(2)
    with repository_database(tmp_path) as database:
        create_project(database)
        create_project(database, 2)
        database.repository.create(initial)
        database.repository.create(other)
        before = table_state(database.engine)
        with pytest.raises(StoryBibleRepositoryError):
            database.repository.append_revision(
                initial.story_bible.id,
                expected_version=ConcurrencyVersion(1),
                title=StoryBibleTitle("Collision"),
                content=StoryBibleContent(),
                clock=lambda: later(),
                revision_id_factory=lambda: other.current_revision.id,
            )
        after = table_state(database.engine)

    assert after == before
