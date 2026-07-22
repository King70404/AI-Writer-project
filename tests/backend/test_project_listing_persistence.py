"""Migrated SQLite Project list reader query and lifecycle tests."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError, StatementError
from tests.backend.project_repository_support import (
    BASE_TIME,
    aggregate,
    project_id,
    repository_database,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.project.application.models import ProjectListPosition
from aiwebnovel.project.errors import ProjectDataCorruption, ProjectRepositoryError
from aiwebnovel.project.persistence.listing import (
    SqlAlchemyProjectListReader,
    project_list_statement,
)
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.integration


def test_empty_database_returns_the_canonical_empty_page(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        page = SqlAlchemyProjectListReader(database.session_factory).list_page(
            limit=20,
            after=None,
        )

    assert page.items == ()
    assert page.has_more is False
    assert page.next_position is None


def test_single_project_returns_current_summary_without_description(tmp_path: Path) -> None:
    value = aggregate(title="Visible title", description="CANARY omitted description")
    with repository_database(tmp_path) as database:
        database.repository.create(value)
        page = SqlAlchemyProjectListReader(database.session_factory).list_page(
            limit=100,
            after=None,
        )

    assert len(page.items) == 1
    item = page.items[0]
    assert item.project_id == str(value.project.id)
    assert item.current_revision_id == str(value.current_revision.id)
    assert item.revision_number == 1
    assert item.concurrency_version == 1
    assert item.title == "Visible title"
    assert not hasattr(item, "description")
    assert "CANARY" not in repr(item)


def test_reader_orders_by_created_at_then_project_id_descending(tmp_path: Path) -> None:
    values = [
        aggregate(1, created_at=BASE_TIME),
        aggregate(2, created_at=BASE_TIME + timedelta(seconds=1)),
        aggregate(3, created_at=BASE_TIME + timedelta(seconds=1)),
    ]
    with repository_database(tmp_path) as database:
        for value in values:
            database.repository.create(value)
        page = SqlAlchemyProjectListReader(database.session_factory).list_page(
            limit=100,
            after=None,
        )

    assert [item.project_id for item in page.items] == [
        str(project_id(3)),
        str(project_id(2)),
        str(project_id(1)),
    ]


@pytest.mark.parametrize("limit", [1, 100])
def test_reader_accepts_limit_boundaries(tmp_path: Path, limit: int) -> None:
    with repository_database(tmp_path) as database:
        database.repository.create(aggregate())
        page = SqlAlchemyProjectListReader(database.session_factory).list_page(
            limit=limit,
            after=None,
        )
    assert len(page.items) == 1


def test_limit_plus_one_sets_cursor_from_last_returned_not_lookahead(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        for value in range(1, 4):
            database.repository.create(
                aggregate(value, created_at=BASE_TIME + timedelta(seconds=value))
            )
        page = SqlAlchemyProjectListReader(database.session_factory).list_page(
            limit=2,
            after=None,
        )

    assert [item.project_id for item in page.items] == [str(project_id(3)), str(project_id(2))]
    assert page.has_more is True
    assert page.next_position == ProjectListPosition(
        created_at=BASE_TIME + timedelta(seconds=2),
        project_id=str(project_id(2)),
    )
    assert str(project_id(1)) not in {item.project_id for item in page.items}


def test_each_page_uses_one_select_without_count_offset_or_description(tmp_path: Path) -> None:
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        database.repository.create(aggregate())

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
            SqlAlchemyProjectListReader(database.session_factory).list_page(
                limit=20,
                after=None,
            )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)

    selects = [
        statement for statement in statements if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) == 1
    normalized = selects[0].upper()
    assert "LEFT OUTER JOIN PROJECT_HEADS" in normalized
    assert "LEFT OUTER JOIN PROJECT_REVISIONS" in normalized
    assert "COUNT(" not in normalized
    assert " OFFSET " not in normalized
    assert "DESCRIPTION" not in normalized
    assert "ORDER BY PROJECTS.CREATED_AT DESC, PROJECTS.ID DESC" in normalized
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for statement in statements
    )


def test_keyset_statement_uses_strict_descending_bound_columns() -> None:
    statement = project_list_statement(
        limit=20,
        after=ProjectListPosition(created_at=BASE_TIME, project_id=str(project_id(5))),
    )
    sql = str(statement).upper()
    assert "PROJECTS.CREATED_AT <" in sql
    assert "PROJECTS.CREATED_AT =" in sql
    assert "PROJECTS.ID <" in sql
    assert "<=" not in sql
    assert "OFFSET" not in sql


def test_reader_reflects_current_revision_and_does_not_load_history(tmp_path: Path) -> None:
    initial = aggregate(title="First", description="Old body")
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        revised = database.repository.append_revision(
            initial.project.id,
            ConcurrencyVersion(1),
            ProjectTitle("Second"),
            ProjectDescription("New body"),
            clock=lambda: BASE_TIME + timedelta(seconds=1),
        )
        page = SqlAlchemyProjectListReader(database.session_factory).list_page(
            limit=20,
            after=None,
        )

    assert len(page.items) == 1
    assert page.items[0].title == "Second"
    assert page.items[0].revision_number == 2
    assert page.items[0].concurrency_version == 2
    assert page.items[0].current_revision_id == str(revised.current_revision.id)
    assert page.items[0].created_at == initial.project.created_at


def test_reader_closes_session_and_returns_connection(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        database.repository.create(aggregate())
        SqlAlchemyProjectListReader(database.session_factory).list_page(limit=20, after=None)
        checked_out = getattr(database.engine.pool, "checkedout", lambda: 0)()
        assert checked_out == 0


def test_reader_converts_database_failure_to_safe_repository_error(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        reader = SqlAlchemyProjectListReader(database.session_factory)
    with pytest.raises(ProjectRepositoryError):
        reader.list_page(limit=20, after=None)


def test_reader_rejects_invalid_public_inputs_before_opening_a_session() -> None:
    calls = 0

    def session_factory() -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("session must not be created")

    reader = SqlAlchemyProjectListReader(session_factory)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        reader.list_page(limit=0, after=None)
    with pytest.raises(TypeError):
        reader.list_page(limit=20, after=object())  # type: ignore[arg-type]
    assert calls == 0


def test_reader_rejects_non_callable_factory() -> None:
    with pytest.raises(TypeError):
        SqlAlchemyProjectListReader(object())  # type: ignore[arg-type]


def test_reader_wraps_session_factory_failure() -> None:
    def fail() -> object:
        raise RuntimeError("private factory failure")

    with pytest.raises(ProjectRepositoryError) as captured:
        SqlAlchemyProjectListReader(fail).list_page(limit=20, after=None)  # type: ignore[arg-type]
    assert "private" not in str(captured.value)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (SQLAlchemyError("private sql"), ProjectRepositoryError),
        (RuntimeError("private runtime"), ProjectRepositoryError),
        (
            StatementError("private", "SELECT", {}, ValueError("bad stored value")),
            ProjectDataCorruption,
        ),
    ],
)
def test_reader_safely_maps_execute_failures(
    failure: Exception,
    expected: type[Exception],
) -> None:
    class FailingSession:
        def __init__(self) -> None:
            self.rolled_back = False
            self.closed = False

        def execute(self, _statement: object) -> object:
            raise failure

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    session = FailingSession()
    reader = SqlAlchemyProjectListReader(lambda: session)  # type: ignore[arg-type,return-value]
    with pytest.raises(expected):
        reader.list_page(limit=20, after=None)
    assert session.rolled_back is True
    assert session.closed is True
