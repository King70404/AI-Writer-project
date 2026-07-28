"""Real SQLite and safe-failure tests for Story Bible revision history."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError, StatementError
from tests.backend.story_bible_repository_support import (
    BASE_TIME,
    create_project,
    repository_database,
    story_bible_aggregate,
    story_bible_id,
    story_bible_revision_id,
)

import aiwebnovel.story_bible.persistence.history_reader as history_module
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.story_bible.application.history_models import (
    StoryBibleRevisionHistoryPosition,
)
from aiwebnovel.story_bible.errors import (
    StoryBibleDataCorruption,
    StoryBibleNotFound,
    StoryBibleRepositoryError,
)
from aiwebnovel.story_bible.persistence.history_reader import (
    SqlAlchemyStoryBibleRevisionHistoryReader,
    _history_item_from_row,
    _snapshot_from_row,
    _StoryBibleHistoryState,
    story_bible_revision_history_statement,
    story_bible_revision_statement,
)
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

pytestmark = pytest.mark.integration


def append_revisions(database: Any, count: int) -> Any:
    current = story_bible_aggregate(title="History 1", content="Body 1")
    create_project(database)
    database.repository.create(current)
    for number in range(2, count + 1):
        current = database.repository.append_revision(
            current.story_bible.id,
            expected_version=ConcurrencyVersion(number - 1),
            title=StoryBibleTitle(f"History {number}"),
            content=StoryBibleContent(f"Body {number}"),
            clock=lambda number=number: BASE_TIME + timedelta(seconds=number - 1),
            revision_id_factory=lambda number=number: story_bible_revision_id(30_000 + number),
        )
    return current


def test_reader_uses_two_read_selects_keyset_and_no_list_content(
    tmp_path: Path,
) -> None:
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        current = append_revisions(database, 3)

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
            page = SqlAlchemyStoryBibleRevisionHistoryReader(
                database.session_factory
            ).list_revisions(
                current.story_bible.id,
                limit=2,
                after=None,
            )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)

    selects = [value for value in statements if value.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2
    history_select = next(
        value
        for value in selects
        if "ORDER BY STORY_BIBLE_REVISIONS.REVISION_NUMBER DESC" in value.upper()
    )
    assert "CONTENT" not in history_select.upper()
    assert "COUNT(" not in history_select.upper()
    assert "OFFSET" not in history_select.upper()
    assert [item.revision_number for item in page.items] == [3, 2]
    assert page.next_position == StoryBibleRevisionHistoryPosition(
        current.story_bible.id,
        RevisionNumber(2),
    )
    assert page.has_more is True
    assert not any(
        value.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for value in statements
    )


def test_multi_page_exact_reads_and_missing_are_stable(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, 3)
        reader = SqlAlchemyStoryBibleRevisionHistoryReader(database.session_factory)
        first = reader.list_revisions(
            current.story_bible.id,
            limit=2,
            after=None,
        )
        assert first.next_position is not None
        second = reader.list_revisions(
            current.story_bible.id,
            limit=2,
            after=first.next_position,
        )
        snapshots = [
            reader.get_revision(current.story_bible.id, RevisionNumber(number))
            for number in (1, 2, 3)
        ]
        missing = reader.get_revision(
            current.story_bible.id,
            RevisionNumber(99),
        )
    assert [item.revision_number for item in (*first.items, *second.items)] == [
        3,
        2,
        1,
    ]
    assert second.has_more is False
    assert second.next_position is None
    assert [value.content for value in snapshots if value is not None] == [
        "Body 1",
        "Body 2",
        "Body 3",
    ]
    assert snapshots[0] is not None and snapshots[0].is_current is False
    assert snapshots[-1] is not None and snapshots[-1].is_current is True
    assert missing is None


def test_head_pointer_not_maximum_revision_number_is_current(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, 1)
        detached_revision_id = story_bible_revision_id(39_999)
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO story_bible_revisions (
                    id, story_bible_id, revision_number, title, content, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(detached_revision_id),
                    str(current.story_bible.id),
                    2,
                    "Detached revision",
                    "Detached body",
                    BASE_TIME,
                ),
            )

        page = SqlAlchemyStoryBibleRevisionHistoryReader(database.session_factory).list_revisions(
            current.story_bible.id,
            limit=20,
            after=None,
        )

    assert page.current_revision_number == 1
    assert [item.revision_number for item in page.items] == [2, 1]
    assert [item.is_current for item in page.items] == [False, True]


def test_twenty_three_revision_keyset_and_old_cursor_remain_stable(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, 23)
        reader = SqlAlchemyStoryBibleRevisionHistoryReader(database.session_factory)
        page_select_counts: list[int] = []
        captured: list[str] = []

        def capture(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            captured.append(statement)

        event.listen(database.engine, "before_cursor_execute", capture)
        try:
            first = reader.list_revisions(
                current.story_bible.id,
                limit=20,
                after=None,
            )
            page_select_counts.append(
                sum(value.lstrip().upper().startswith("SELECT") for value in captured)
            )
            captured.clear()
            current = database.repository.append_revision(
                current.story_bible.id,
                expected_version=ConcurrencyVersion(23),
                title=StoryBibleTitle("History 24"),
                content=StoryBibleContent("Body 24"),
                clock=lambda: BASE_TIME + timedelta(seconds=23),
                revision_id_factory=lambda: story_bible_revision_id(30_024),
            )
            captured.clear()
            assert first.next_position is not None
            second = reader.list_revisions(
                current.story_bible.id,
                limit=20,
                after=first.next_position,
            )
            page_select_counts.append(
                sum(value.lstrip().upper().startswith("SELECT") for value in captured)
            )
            captured.clear()
            newest = reader.list_revisions(
                current.story_bible.id,
                limit=20,
                after=None,
            )
            page_select_counts.append(
                sum(value.lstrip().upper().startswith("SELECT") for value in captured)
            )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)

    merged = [item.revision_number for item in (*first.items, *second.items)]
    assert merged == list(range(23, 0, -1))
    assert len(set(merged)) == 23
    assert first.has_more is True
    assert second.has_more is False
    assert [item.is_current for item in first.items].count(True) == 1
    assert first.items[0].is_current is True
    assert newest.items[0].revision_number == 24
    assert newest.items[0].is_current is True
    assert page_select_counts == [2, 2, 2]


def test_statements_have_exact_owner_bound_keyset_and_body_shape() -> None:
    history = str(
        story_bible_revision_history_statement(
            story_bible_id=story_bible_id(1),
            limit=20,
            after=RevisionNumber(2),
        )
    ).upper()
    exact = str(
        story_bible_revision_statement(
            story_bible_id=story_bible_id(1),
            revision_number=RevisionNumber(1),
        )
    ).upper()
    assert "STORY_BIBLE_REVISIONS.STORY_BIBLE_ID =" in history
    assert "STORY_BIBLE_REVISIONS.REVISION_NUMBER <" in history
    assert "<=" not in history
    assert "CONTENT" not in history
    assert "OFFSET" not in history
    assert "STORY_BIBLE_REVISIONS.STORY_BIBLE_ID =" in exact
    assert "STORY_BIBLE_REVISIONS.REVISION_NUMBER =" in exact
    assert "CONTENT" in exact


def test_missing_owner_and_corrupt_missing_head_are_distinct(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        reader = SqlAlchemyStoryBibleRevisionHistoryReader(database.session_factory)
        with pytest.raises(StoryBibleNotFound):
            reader.list_revisions(story_bible_id(404), limit=20, after=None)

        current = append_revisions(database, 1)
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM story_bible_heads WHERE story_bible_id = ?",
                (str(current.story_bible.id),),
            )
        with pytest.raises(StoryBibleDataCorruption):
            reader.get_revision(
                current.story_bible.id,
                RevisionNumber(1),
            )


def state() -> _StoryBibleHistoryState:
    return _StoryBibleHistoryState(
        story_bible_id=story_bible_id(1),
        project_id=story_bible_aggregate().story_bible.project_id,
        current_revision_id=story_bible_revision_id(20_001),
        current_revision_number=RevisionNumber(1),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


@pytest.mark.parametrize(
    "row",
    [
        ("bad", RevisionNumber(1), "Title", BASE_TIME),
        (story_bible_revision_id(20_001), 1, "Title", BASE_TIME),
        (story_bible_revision_id(20_001), RevisionNumber(1), 1, BASE_TIME),
        (
            story_bible_revision_id(20_001),
            RevisionNumber(1),
            " Title ",
            BASE_TIME,
        ),
        (
            story_bible_revision_id(20_001),
            RevisionNumber(1),
            "Title",
            BASE_TIME - timedelta(seconds=1),
        ),
    ],
)
def test_corrupt_list_rows_fail_without_text_leak(row: tuple[object, ...]) -> None:
    with pytest.raises(StoryBibleDataCorruption) as captured:
        _history_item_from_row(row, state=state())  # type: ignore[arg-type]
    assert "Title" not in str(captured.value)


@pytest.mark.parametrize(
    "row",
    [
        ("bad", RevisionNumber(1), "Title", "Body", BASE_TIME),
        (
            story_bible_revision_id(20_001),
            RevisionNumber(1),
            1,
            "Body",
            BASE_TIME,
        ),
        (
            story_bible_revision_id(20_001),
            RevisionNumber(1),
            "Title",
            1,
            BASE_TIME,
        ),
        (
            story_bible_revision_id(20_001),
            RevisionNumber(1),
            " Title ",
            "Body",
            BASE_TIME,
        ),
        (
            story_bible_revision_id(20_001),
            RevisionNumber(1),
            "Title",
            "Body\r\n",
            BASE_TIME,
        ),
    ],
)
def test_corrupt_snapshot_rows_fail_without_body_leak(
    row: tuple[object, ...],
) -> None:
    with pytest.raises(StoryBibleDataCorruption) as captured:
        _snapshot_from_row(row, state=state())  # type: ignore[arg-type]
    assert "Body" not in str(captured.value)


class FailingSession:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.rollback_calls = 0
        self.close_calls = 0

    def execute(self, _statement: object) -> None:
        raise self.error

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def failure(kind: str) -> Exception:
    if kind == "statement-domain":
        return StatementError("safe", None, None, ValueError("CANARY"))
    if kind == "statement-driver":
        return StatementError("safe", None, None, RuntimeError("CANARY"))
    if kind == "sqlalchemy":
        return SQLAlchemyError("CANARY")
    return RuntimeError("CANARY")


@pytest.mark.parametrize(
    ("operation", "kind", "expected"),
    [
        ("list", "statement-domain", StoryBibleDataCorruption),
        ("list", "statement-driver", StoryBibleRepositoryError),
        ("list", "sqlalchemy", StoryBibleRepositoryError),
        ("list", "runtime", StoryBibleRepositoryError),
        ("get", "statement-domain", StoryBibleDataCorruption),
        ("get", "statement-driver", StoryBibleRepositoryError),
        ("get", "sqlalchemy", StoryBibleRepositoryError),
        ("get", "runtime", StoryBibleRepositoryError),
    ],
)
def test_database_failures_are_safe_rollback_and_close(
    operation: str,
    kind: str,
    expected: type[Exception],
) -> None:
    session = FailingSession(failure(kind))
    reader = SqlAlchemyStoryBibleRevisionHistoryReader(
        lambda: session  # type: ignore[arg-type]
    )
    with pytest.raises(expected) as captured:
        if operation == "list":
            reader.list_revisions(story_bible_id(1), limit=20, after=None)
        else:
            reader.get_revision(story_bible_id(1), RevisionNumber(1))
    assert "CANARY" not in str(captured.value)
    assert session.rollback_calls == 1
    assert session.close_calls == 1


def test_reader_boundary_and_session_factory_failures_do_not_leak() -> None:
    with pytest.raises(TypeError):
        SqlAlchemyStoryBibleRevisionHistoryReader(object())  # type: ignore[arg-type]
    reader = SqlAlchemyStoryBibleRevisionHistoryReader(
        lambda: (_ for _ in ()).throw(RuntimeError("CANARY"))
    )
    with pytest.raises(TypeError):
        reader.list_revisions("bad", limit=20, after=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        reader.list_revisions(story_bible_id(1), limit=0, after=None)
    with pytest.raises(TypeError):
        reader.list_revisions(story_bible_id(1), limit=20, after=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        reader.list_revisions(
            story_bible_id(1),
            limit=20,
            after=StoryBibleRevisionHistoryPosition(
                story_bible_id(2),
                RevisionNumber(1),
            ),
        )
    with pytest.raises(TypeError):
        reader.get_revision(story_bible_id(1), 1)  # type: ignore[arg-type]
    with pytest.raises(StoryBibleRepositoryError) as captured:
        reader.get_revision(story_bible_id(1), RevisionNumber(1))
    assert "CANARY" not in str(captured.value)


def test_invalid_current_state_row_is_corruption() -> None:
    with pytest.raises(StoryBibleDataCorruption):
        history_module._state_from_row(
            (
                story_bible_id(1),
                story_bible_aggregate().story_bible.project_id,
                ConcurrencyVersion(1),
                BASE_TIME,
                BASE_TIME,
                story_bible_aggregate().story_bible.project_id,
                story_bible_id(1),
                story_bible_revision_id(20_001),
                BASE_TIME,
                story_bible_revision_id(20_001),
                story_bible_id(1),
                RevisionNumber(2),
                BASE_TIME,
            )
        )


class EmptyResult:
    def tuples(self) -> EmptyResult:
        return self

    def all(self) -> list[object]:
        return []


class EmptyHistorySession:
    def __init__(self, real: Any) -> None:
        self.real = real
        self.execute_calls = 0

    def execute(self, statement: object) -> Any:
        self.execute_calls += 1
        return self.real.execute(statement) if self.execute_calls == 1 else EmptyResult()

    def rollback(self) -> None:
        self.real.rollback()

    def close(self) -> None:
        self.real.close()


def test_empty_first_page_and_mapping_type_failures_are_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, 1)
        reader = SqlAlchemyStoryBibleRevisionHistoryReader(
            lambda: EmptyHistorySession(database.session_factory())  # type: ignore[arg-type]
        )
        with pytest.raises(StoryBibleDataCorruption):
            reader.list_revisions(
                current.story_bible.id,
                limit=20,
                after=None,
            )

        real_reader = SqlAlchemyStoryBibleRevisionHistoryReader(database.session_factory)
        monkeypatch.setattr(
            history_module,
            "_history_item_from_row",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("CANARY")),
        )
        with pytest.raises(StoryBibleDataCorruption) as captured:
            real_reader.list_revisions(
                current.story_bible.id,
                limit=20,
                after=None,
            )
        assert "CANARY" not in str(captured.value)


def test_snapshot_mapping_type_failure_is_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, 1)
        monkeypatch.setattr(
            history_module,
            "_snapshot_from_row",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("CANARY")),
        )
        with pytest.raises(StoryBibleDataCorruption) as captured:
            SqlAlchemyStoryBibleRevisionHistoryReader(database.session_factory).get_revision(
                current.story_bible.id,
                RevisionNumber(1),
            )
        assert "CANARY" not in str(captured.value)


def test_load_state_converts_mapping_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        def tuples(self) -> Result:
            return self

        def one_or_none(self) -> tuple[object, ...]:
            return (object(),) * 13

    class Session:
        def execute(self, _statement: object) -> Result:
            return Result()

    def fail(_row: object) -> None:
        raise TypeError("CANARY")

    monkeypatch.setattr(history_module, "_state_from_row", fail)
    with pytest.raises(StoryBibleDataCorruption) as captured:
        SqlAlchemyStoryBibleRevisionHistoryReader._load_state(
            Session(),  # type: ignore[arg-type]
            story_bible_id(1),
        )
    assert "CANARY" not in str(captured.value)
