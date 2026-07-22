"""Atomic Project aggregate creation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.backend.project_repository_support import (
    aggregate,
    repository_database,
    table_state,
)

from aiwebnovel.project.errors import (
    ProjectAlreadyExists,
    ProjectPersistenceConflict,
)

pytestmark = pytest.mark.integration


def test_create_atomically_inserts_project_revision_and_head(tmp_path: Path) -> None:
    initial = aggregate(title="Create canary", description="Created once")
    with repository_database(tmp_path) as database:
        returned = database.repository.create(initial)
        state = table_state(database.engine)

    assert returned == initial
    assert state == {
        "projects": 1,
        "project_revisions": 1,
        "project_heads": 1,
        "concurrency_version": 1,
        "head_revision_id": str(initial.current_revision.id),
    }


def test_duplicate_project_id_has_specific_safe_error_without_changes(tmp_path: Path) -> None:
    initial = aggregate(title="Repository canary title")
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        before = table_state(database.engine)
        with pytest.raises(ProjectAlreadyExists) as captured:
            database.repository.create(initial)
        after = table_state(database.engine)

    assert captured.value.project_id == initial.project.id
    assert "Repository canary title" not in str(captured.value)
    assert after == before


def test_duplicate_revision_id_rolls_back_new_project_and_is_not_project_duplicate(
    tmp_path: Path,
) -> None:
    existing = aggregate(1, revision_value=90)
    colliding = aggregate(2, revision_value=90)
    with repository_database(tmp_path) as database:
        database.repository.create(existing)
        with pytest.raises(ProjectPersistenceConflict):
            database.repository.create(colliding)
        state = table_state(database.engine)
        assert database.repository.get(colliding.project.id) is None

    assert state["projects"] == 1
    assert state["project_revisions"] == 1
    assert state["project_heads"] == 1


def test_head_insert_failure_rolls_back_project_and_revision(tmp_path: Path) -> None:
    initial = aggregate()
    with repository_database(tmp_path) as database:
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER test_fail_project_head_insert "
                "BEFORE INSERT ON project_heads BEGIN "
                "SELECT RAISE(ABORT, 'controlled head failure'); END"
            )
        try:
            with pytest.raises(ProjectPersistenceConflict):
                database.repository.create(initial)
            state = table_state(database.engine)
        finally:
            with database.engine.begin() as connection:
                connection.exec_driver_sql("DROP TRIGGER test_fail_project_head_insert")

    assert state["projects"] == 0
    assert state["project_revisions"] == 0
    assert state["project_heads"] == 0
