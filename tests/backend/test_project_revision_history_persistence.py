"""Migrated SQLite immutable Project revision-history reader tests."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event
from tests.backend.project_repository_support import (
    BASE_TIME,
    aggregate,
    later,
    repository_database,
    revision_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.persistence.history import (
    SqlAlchemyProjectRevisionHistoryReader,
    project_revision_history_statement,
    project_revision_statement,
)
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.integration


def append_revisions(
    database: object,
    *,
    count: int,
    marker: str = "History",
) -> ProjectAggregate:
    repository = database.repository  # type: ignore[attr-defined]
    current = aggregate(title=f"{marker} 1", description=f"{marker} body 1")
    repository.create(current)
    for number in range(2, count + 1):
        current = repository.append_revision(
            current.project.id,
            ConcurrencyVersion(number - 1),
            ProjectTitle(f"{marker} {number}"),
            ProjectDescription(f"{marker} body {number}"),
            clock=lambda number=number: BASE_TIME + timedelta(seconds=number - 1),
            revision_id_factory=lambda number=number: revision_id(20_000 + number),
        )
    return current


def test_new_project_has_one_current_revision_without_list_description(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, count=1)
        page = SqlAlchemyProjectRevisionHistoryReader(database.session_factory).list_page(
            project_id=current.project.id, limit=20, after=None
        )

    assert [item.revision_number for item in page.items] == [1]
    assert page.current_revision_number == 1
    assert page.items[0].is_current is True
    assert not hasattr(page.items[0], "description")
    assert "body" not in repr(page.items[0])


def test_three_revisions_list_descending_and_get_original_bodies(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, count=3)
        reader = SqlAlchemyProjectRevisionHistoryReader(database.session_factory)
        page = reader.list_page(project_id=current.project.id, limit=20, after=None)
        snapshots = [
            reader.get_revision(
                project_id=current.project.id,
                revision_number=RevisionNumber(number),
            )
            for number in (1, 2, 3)
        ]

    assert [item.revision_number for item in page.items] == [3, 2, 1]
    assert [item.is_current for item in page.items] == [True, False, False]
    assert [value.title for value in snapshots if value is not None] == [
        "History 1",
        "History 2",
        "History 3",
    ]
    assert [value.description for value in snapshots if value is not None] == [
        "History body 1",
        "History body 2",
        "History body 3",
    ]
    assert snapshots[0] is not None and snapshots[0].is_current is False
    assert snapshots[2] is not None and snapshots[2].is_current is True


@pytest.mark.parametrize("limit", [1, 20, 100])
def test_reader_accepts_history_limit_boundaries(tmp_path: Path, limit: int) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, count=2)
        page = SqlAlchemyProjectRevisionHistoryReader(database.session_factory).list_page(
            project_id=current.project.id, limit=limit, after=None
        )
    assert len(page.items) == min(limit, 2)


def test_list_uses_two_selects_and_history_select_omits_body_count_and_offset(
    tmp_path: Path,
) -> None:
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        current = append_revisions(database, count=3)

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
            SqlAlchemyProjectRevisionHistoryReader(database.session_factory).list_page(
                project_id=current.project.id, limit=2, after=None
            )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)

    selects = [
        statement for statement in statements if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) == 2
    history_select = next(
        statement
        for statement in selects
        if "ORDER BY PROJECT_REVISIONS.REVISION_NUMBER DESC" in statement.upper()
    )
    normalized = history_select.upper()
    assert "DESCRIPTION" not in normalized
    assert "COUNT(" not in normalized
    assert " OFFSET " not in normalized
    assert "LIMIT ?" in normalized
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for statement in statements
    )


def test_exact_revision_uses_two_selects_and_returns_none_only_for_missing_revision(
    tmp_path: Path,
) -> None:
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        current = append_revisions(database, count=2)

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
            missing = SqlAlchemyProjectRevisionHistoryReader(database.session_factory).get_revision(
                project_id=current.project.id,
                revision_number=RevisionNumber(99),
            )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)

    assert missing is None
    selects = [value for value in statements if value.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2
    assert "DESCRIPTION" in selects[-1].upper()
    assert not any(
        value.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for value in statements
    )


def test_statement_shapes_use_bound_strict_keyset_and_exact_owner() -> None:
    value = aggregate()
    history = str(
        project_revision_history_statement(
            project_id=value.project.id,
            limit=20,
            after=RevisionNumber(2),
        )
    ).upper()
    exact = str(
        project_revision_statement(
            project_id=value.project.id,
            revision_number=RevisionNumber(1),
        )
    ).upper()
    assert "PROJECT_REVISIONS.PROJECT_ID =" in history
    assert "PROJECT_REVISIONS.REVISION_NUMBER <" in history
    assert "<=" not in history
    assert "OFFSET" not in history
    assert "DESCRIPTION" not in history
    assert "PROJECT_REVISIONS.PROJECT_ID =" in exact
    assert "PROJECT_REVISIONS.REVISION_NUMBER =" in exact


def test_revision_timestamps_remain_unchanged_after_later_appends(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, count=2)
        reader = SqlAlchemyProjectRevisionHistoryReader(database.session_factory)
        first = reader.get_revision(
            project_id=current.project.id,
            revision_number=RevisionNumber(1),
        )
        database.repository.append_revision(
            current.project.id,
            ConcurrencyVersion(2),
            ProjectTitle("History 3"),
            ProjectDescription("History body 3"),
            clock=lambda: later(4),
            revision_id_factory=lambda: revision_id(30_003),
        )
        again = reader.get_revision(
            project_id=current.project.id,
            revision_number=RevisionNumber(1),
        )
    assert first is not None and again is not None
    assert (
        first.project_id,
        first.revision_id,
        first.revision_number,
        first.title,
        first.description,
        first.created_at,
        first.is_current,
    ) == (
        again.project_id,
        again.revision_id,
        again.revision_number,
        again.title,
        again.description,
        again.created_at,
        again.is_current,
    )
    assert first.current_revision_number == 2
    assert again.current_revision_number == 3
