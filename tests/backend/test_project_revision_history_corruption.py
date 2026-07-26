"""Safe failure tests for corrupted Project revision-history state."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError, StatementError
from tests.backend.project_repository_support import aggregate, repository_database, revision_id

import aiwebnovel.project.persistence.history as history_module
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.errors import (
    ProjectDataCorruption,
    ProjectNotFound,
    ProjectRepositoryError,
)
from aiwebnovel.project.persistence.history import (
    SqlAlchemyProjectRevisionHistoryReader,
    _history_item_from_row,
    _history_snapshot_from_row,
    _ProjectHistoryState,
)

pytestmark = pytest.mark.integration


def test_missing_project_is_distinct_from_corrupted_history(tmp_path: Path) -> None:
    value = aggregate()
    with repository_database(tmp_path) as database:
        reader = SqlAlchemyProjectRevisionHistoryReader(database.session_factory)
        with pytest.raises(ProjectNotFound):
            reader.list_page(project_id=value.project.id, limit=20, after=None)
        with pytest.raises(ProjectNotFound):
            reader.get_revision(
                project_id=value.project.id,
                revision_number=RevisionNumber(1),
            )


def test_project_without_head_fails_the_whole_read_without_repair(tmp_path: Path) -> None:
    value = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(value)
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM project_heads WHERE project_id = ?",
                (str(value.project.id),),
            )
        reader = SqlAlchemyProjectRevisionHistoryReader(database.session_factory)
        with pytest.raises(ProjectDataCorruption):
            reader.list_page(project_id=value.project.id, limit=20, after=None)
        with database.engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT COUNT(*) FROM project_heads").scalar_one() == 0
            )


def test_head_pointing_to_missing_revision_is_safe_corruption(tmp_path: Path) -> None:
    value = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(value)
        database.engine.dispose()
        path = Path(str(database.engine.url.database))
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "UPDATE project_heads SET revision_id = ? WHERE project_id = ?",
                (str(revision_id(99_999)), str(value.project.id)),
            )
            connection.commit()
        reader = SqlAlchemyProjectRevisionHistoryReader(database.session_factory)
        with pytest.raises(ProjectDataCorruption):
            reader.get_revision(
                project_id=value.project.id,
                revision_number=RevisionNumber(1),
            )


def test_invalid_history_row_fails_entire_page_without_body_leak(tmp_path: Path) -> None:
    value = aggregate()
    canary = "HISTORY_CORRUPTION_CANARY"
    with repository_database(tmp_path) as database:
        database.repository.create(value)
        with database.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA ignore_check_constraints = ON")
            connection.exec_driver_sql(
                "INSERT INTO project_revisions "
                "(id, project_id, revision_number, title, description, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(revision_id(88_888)),
                    str(value.project.id),
                    2,
                    "   ",
                    canary,
                    value.project.created_at.replace(tzinfo=None),
                ),
            )
        reader = SqlAlchemyProjectRevisionHistoryReader(database.session_factory)
        with pytest.raises(ProjectDataCorruption) as captured:
            reader.list_page(project_id=value.project.id, limit=20, after=None)
        assert canary not in str(captured.value)
        with database.engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT COUNT(*) FROM project_revisions").scalar_one()
                == 2
            )


def test_invalid_exact_revision_description_fails_without_partial_snapshot(
    tmp_path: Path,
) -> None:
    value = aggregate()
    canary = "HISTORY_BODY_CANARY\x01"
    with repository_database(tmp_path) as database:
        database.repository.create(value)
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO project_revisions "
                "(id, project_id, revision_number, title, description, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(revision_id(77_777)),
                    str(value.project.id),
                    2,
                    "Valid title",
                    canary,
                    value.project.created_at.replace(tzinfo=None),
                ),
            )
        reader = SqlAlchemyProjectRevisionHistoryReader(database.session_factory)
        with pytest.raises(ProjectDataCorruption) as captured:
            reader.get_revision(
                project_id=value.project.id,
                revision_number=RevisionNumber(2),
            )
        assert canary not in str(captured.value)


def test_reader_input_and_session_factory_failures_are_safe() -> None:
    reader = SqlAlchemyProjectRevisionHistoryReader(
        lambda: (_ for _ in ()).throw(RuntimeError("CANARY"))
    )
    value = aggregate()
    with pytest.raises(ProjectRepositoryError) as captured:
        reader.list_page(project_id=value.project.id, limit=20, after=None)
    assert "CANARY" not in str(captured.value)
    with pytest.raises(TypeError):
        SqlAlchemyProjectRevisionHistoryReader(object())  # type: ignore[arg-type]


def test_reader_rejects_boundary_types_before_opening_a_session() -> None:
    value = aggregate()
    reader = SqlAlchemyProjectRevisionHistoryReader(
        lambda: (_ for _ in ()).throw(AssertionError("session must not open"))
    )
    with pytest.raises(TypeError):
        reader.list_page(project_id=str(value.project.id), limit=20, after=None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        reader.list_page(project_id=value.project.id, limit=20, after=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        reader.get_revision(project_id=value.project.id, revision_number=1)  # type: ignore[arg-type]


def _history_state() -> tuple[Any, _ProjectHistoryState]:
    value = aggregate()
    return value, _ProjectHistoryState(
        project_id=value.project.id,
        current_revision_id=value.current_revision.id,
        current_revision_number=value.current_revision.revision_number,
        created_at=value.project.created_at,
        updated_at=value.project.updated_at,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision_id", "not-a-revision-id"),
        ("project_id", aggregate(2).project.id),
        ("revision_number", 1),
        ("title", 1),
        ("created_at", "not-a-datetime"),
    ],
)
def test_history_row_type_or_owner_corruption_is_rejected(
    field: str,
    value: object,
) -> None:
    aggregate_value, state = _history_state()
    row: dict[str, object] = {
        "revision_id": aggregate_value.current_revision.id,
        "project_id": aggregate_value.project.id,
        "revision_number": aggregate_value.current_revision.revision_number,
        "title": str(aggregate_value.current_revision.title),
        "created_at": aggregate_value.current_revision.created_at,
    }
    row[field] = value
    with pytest.raises(ProjectDataCorruption):
        _history_item_from_row(tuple(row.values()), state=state)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "title,created_at_offset",
    [
        (" Repository project ", 0),
        ("Repository project", -1),
        ("Repository project", 1),
    ],
)
def test_history_row_noncanonical_text_or_time_is_rejected(
    title: str,
    created_at_offset: int,
) -> None:
    value, state = _history_state()
    row = (
        value.current_revision.id,
        value.project.id,
        value.current_revision.revision_number,
        title,
        value.current_revision.created_at + timedelta(seconds=created_at_offset),
    )
    with pytest.raises(ProjectDataCorruption):
        _history_item_from_row(row, state=state)


@pytest.mark.parametrize(
    "field,value",
    [
        ("description", 1),
        ("project_id", aggregate(2).project.id),
        ("title", " Repository project "),
        ("description", "Repository\r\ndescription"),
    ],
)
def test_snapshot_row_corruption_is_rejected(field: str, value: object) -> None:
    aggregate_value, state = _history_state()
    row: dict[str, object] = {
        "revision_id": aggregate_value.current_revision.id,
        "project_id": aggregate_value.project.id,
        "revision_number": aggregate_value.current_revision.revision_number,
        "title": str(aggregate_value.current_revision.title),
        "description": str(aggregate_value.current_revision.description),
        "created_at": aggregate_value.current_revision.created_at,
    }
    row[field] = value
    with pytest.raises(ProjectDataCorruption):
        _history_snapshot_from_row(tuple(row.values()), state=state)  # type: ignore[arg-type]


class _FailingSession:
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


def _failure(kind: str) -> Exception:
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
        ("list", "statement-domain", ProjectDataCorruption),
        ("list", "statement-driver", ProjectRepositoryError),
        ("list", "sqlalchemy", ProjectRepositoryError),
        ("list", "runtime", ProjectRepositoryError),
        ("get", "statement-domain", ProjectDataCorruption),
        ("get", "statement-driver", ProjectRepositoryError),
        ("get", "sqlalchemy", ProjectRepositoryError),
        ("get", "runtime", ProjectRepositoryError),
    ],
)
def test_reader_translates_database_failures_and_always_closes(
    operation: str,
    kind: str,
    expected: type[Exception],
) -> None:
    value = aggregate()
    session = _FailingSession(_failure(kind))
    reader = SqlAlchemyProjectRevisionHistoryReader(lambda: session)  # type: ignore[arg-type]
    with pytest.raises(expected) as captured:
        if operation == "list":
            reader.list_page(project_id=value.project.id, limit=20, after=None)
        else:
            reader.get_revision(
                project_id=value.project.id,
                revision_number=RevisionNumber(1),
            )
    assert "CANARY" not in str(captured.value)
    assert session.rollback_calls == 1
    assert session.close_calls == 1


class _EmptyHistoryResult:
    def tuples(self) -> _EmptyHistoryResult:
        return self

    def all(self) -> list[object]:
        return []


class _EmptyHistorySession:
    def __init__(self, session: Any) -> None:
        self.session = session
        self.execute_calls = 0

    def execute(self, statement: object) -> Any:
        self.execute_calls += 1
        if self.execute_calls == 1:
            return self.session.execute(statement)
        return _EmptyHistoryResult()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()


def test_existing_project_with_an_empty_initial_history_page_is_corruption(
    tmp_path: Path,
) -> None:
    value = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(value)
        reader = SqlAlchemyProjectRevisionHistoryReader(
            lambda: _EmptyHistorySession(database.session_factory())  # type: ignore[arg-type]
        )
        with pytest.raises(ProjectDataCorruption):
            reader.list_page(project_id=value.project.id, limit=20, after=None)


class _OneRowSession:
    def __init__(self, row: tuple[object, object, object]) -> None:
        self.row = row

    def execute(self, _statement: object) -> _OneRowSession:
        return self

    def one_or_none(self) -> tuple[object, object, object]:
        return self.row


def test_invalid_mapped_current_state_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    value = aggregate()
    revision_record = SimpleNamespace(
        title=str(value.current_revision.title),
        description=str(value.current_revision.description),
    )
    invalid_aggregate = SimpleNamespace(
        project=SimpleNamespace(
            id=value.project.id,
            concurrency_version=1,
            created_at=value.project.created_at,
            updated_at=value.project.updated_at,
        ),
        current_revision=value.current_revision,
    )
    monkeypatch.setattr(
        history_module,
        "project_aggregate_from_records",
        lambda *_records: invalid_aggregate,
    )
    with pytest.raises(ProjectDataCorruption):
        SqlAlchemyProjectRevisionHistoryReader._load_state(
            _OneRowSession((object(), object(), revision_record)),  # type: ignore[arg-type]
            value.project.id,
        )


def test_current_state_mapping_domain_failure_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = aggregate()

    def fail_mapping(*_records: object) -> None:
        raise TypeError("CANARY")

    monkeypatch.setattr(
        history_module,
        "project_aggregate_from_records",
        fail_mapping,
    )
    with pytest.raises(ProjectDataCorruption) as captured:
        SqlAlchemyProjectRevisionHistoryReader._load_state(
            _OneRowSession((object(), object(), object())),  # type: ignore[arg-type]
            value.project.id,
        )
    assert "CANARY" not in str(captured.value)
