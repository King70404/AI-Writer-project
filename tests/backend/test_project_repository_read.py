"""Consistent current Project aggregate read tests."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest
from sqlalchemy import event
from tests.backend.project_repository_support import (
    aggregate,
    later,
    project_id,
    repository_database,
    table_state,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.integration


def test_get_missing_project_returns_none_without_writes(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        assert database.repository.get(project_id(404)) is None
        assert table_state(database.engine)["projects"] == 0


def test_get_uses_one_business_select_and_does_not_load_history(tmp_path: Path) -> None:
    initial = aggregate()
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        database.repository.append_revision(
            initial.project.id,
            ConcurrencyVersion(1),
            ProjectTitle("Second"),
            ProjectDescription("Current only"),
            clock=lambda: later(),
        )

        def capture_statement(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(database.engine, "before_cursor_execute", capture_statement)
        try:
            restored = database.repository.get(initial.project.id)
        finally:
            event.remove(database.engine, "before_cursor_execute", capture_statement)

    assert restored is not None
    assert int(restored.current_revision.revision_number) == 2
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


def test_get_returns_aware_values_usable_after_session_close_and_preserves_state(
    tmp_path: Path,
) -> None:
    initial = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        before = table_state(database.engine)
        restored = database.repository.get(initial.project.id)
        after = table_state(database.engine)

    assert restored is not None
    assert restored == initial
    assert restored.project.created_at.tzinfo is UTC
    assert str(restored.current_revision.title) == "Repository project"
    assert after == before
