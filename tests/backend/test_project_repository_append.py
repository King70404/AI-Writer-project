"""Atomic immutable Project revision append tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import event
from tests.backend.project_repository_support import (
    aggregate,
    later,
    project_id,
    repository_database,
    revision_id,
    table_state,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.project.errors import ProjectNotFound, ProjectPersistenceConflict
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.integration


def test_append_inserts_revision_and_conditionally_moves_project_and_head(
    tmp_path: Path,
) -> None:
    initial = aggregate()
    statements: list[str] = []
    with repository_database(tmp_path) as database:
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
                initial.project.id,
                ConcurrencyVersion(1),
                ProjectTitle("Second revision"),
                ProjectDescription("Changed without replacing history"),
                clock=lambda: later(),
                revision_id_factory=lambda: revision_id(20_002),
            )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture_write)

        restored = database.repository.get(initial.project.id)
        state = table_state(database.engine)
        with database.engine.connect() as connection:
            history = connection.exec_driver_sql(
                "SELECT id, revision_number, title FROM project_revisions "
                "WHERE project_id = ? ORDER BY revision_number",
                (str(initial.project.id),),
            ).all()

    assert restored == appended
    assert int(appended.project.concurrency_version) == 2
    assert int(appended.current_revision.revision_number) == 2
    assert appended.head.revision_id == appended.current_revision.id
    assert state == {
        "projects": 1,
        "project_revisions": 2,
        "project_heads": 1,
        "concurrency_version": 2,
        "head_revision_id": str(revision_id(20_002)),
    }
    assert history == [
        (str(initial.current_revision.id), 1, "Repository project"),
        (str(revision_id(20_002)), 2, "Second revision"),
    ]
    assert len(statements) == 3
    project_cas = next(
        statement for statement in statements if statement.startswith("UPDATE projects")
    )
    head_cas = next(
        statement for statement in statements if statement.startswith("UPDATE project_heads")
    )
    assert "projects.id = ?" in project_cas
    assert "projects.concurrency_version = ?" in project_cas
    assert "project_heads.project_id = ?" in head_cas
    assert "project_heads.revision_id = ?" in head_cas


def test_append_missing_project_rejects_before_clock_and_id_factory(tmp_path: Path) -> None:
    calls = {"clock": 0, "id": 0}

    def clock() -> object:
        calls["clock"] += 1
        return later()

    def identifier_factory() -> object:
        calls["id"] += 1
        return revision_id(999)

    with repository_database(tmp_path) as database, pytest.raises(ProjectNotFound):
        database.repository.append_revision(
            project_id(404),
            ConcurrencyVersion(1),
            ProjectTitle("Missing"),
            ProjectDescription(),
            clock=clock,  # type: ignore[arg-type]
            revision_id_factory=identifier_factory,  # type: ignore[arg-type]
        )

    assert calls == {"clock": 0, "id": 0}


def test_stale_append_rejects_before_clock_id_or_database_write(tmp_path: Path) -> None:
    initial = aggregate()
    calls = {"clock": 0, "id": 0}

    def clock() -> object:
        calls["clock"] += 1
        return later(2)

    def identifier_factory() -> object:
        calls["id"] += 1
        return revision_id(30_003)

    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        database.repository.append_revision(
            initial.project.id,
            ConcurrencyVersion(1),
            ProjectTitle("Second"),
            ProjectDescription(),
            clock=lambda: later(),
            revision_id_factory=lambda: revision_id(30_002),
        )
        before = table_state(database.engine)
        with pytest.raises(ConcurrencyConflict) as captured:
            database.repository.append_revision(
                initial.project.id,
                ConcurrencyVersion(1),
                ProjectTitle("Stale canary title"),
                ProjectDescription("Must not persist"),
                clock=clock,  # type: ignore[arg-type]
                revision_id_factory=identifier_factory,  # type: ignore[arg-type]
            )
        after = table_state(database.engine)

    assert captured.value.expected_version == 1
    assert captured.value.actual_version == 2
    assert calls == {"clock": 0, "id": 0}
    assert after == before


def test_duplicate_new_revision_id_rolls_back_append(tmp_path: Path) -> None:
    initial = aggregate()
    other = aggregate(2)
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        database.repository.create(other)
        before = table_state(database.engine)
        with pytest.raises(ProjectPersistenceConflict):
            database.repository.append_revision(
                initial.project.id,
                ConcurrencyVersion(1),
                ProjectTitle("Collision"),
                ProjectDescription(),
                clock=lambda: later(),
                revision_id_factory=lambda: other.current_revision.id,
            )
        after = table_state(database.engine)

    assert after == before
