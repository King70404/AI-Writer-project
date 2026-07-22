"""Project repository rollback and Session lifecycle tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import ClassVar

import pytest
from sqlalchemy import update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
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
from aiwebnovel.project.errors import (
    ProjectNotFound,
    ProjectPersistenceConflict,
    ProjectRepositoryError,
)
from aiwebnovel.project.persistence import repository as repository_module
from aiwebnovel.project.persistence.models import ProjectHeadRecord
from aiwebnovel.project.persistence.repository import SqlAlchemyProjectRepository
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.integration


class TrackingSession(Session):
    """Test Session recording cleanup calls without changing transaction behavior."""

    instances: ClassVar[list[TrackingSession]] = []

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.rollback_called = False
        self.close_called = False
        type(self).instances.append(self)

    def rollback(self) -> None:
        self.rollback_called = True
        super().rollback()

    def close(self) -> None:
        self.close_called = True
        super().close()


class CommitFailingSession(TrackingSession):
    """Test Session that raises before a database commit can complete."""

    def commit(self) -> None:
        raise OperationalError(
            "COMMIT canary SQL",
            {"secret": "Commit canary body"},
            sqlite3.OperationalError("controlled commit failure"),
        )


class UnexpectedCommitFailureSession(TrackingSession):
    """Test Session that raises one non-SQLAlchemy commit failure."""

    def commit(self) -> None:
        raise RuntimeError("unexpected commit details")


def tracking_factory(
    database: object,
    session_type: type[Session] = TrackingSession,
) -> sessionmaker[Session]:
    engine = database.engine  # type: ignore[attr-defined]
    return sessionmaker(
        bind=engine,
        class_=session_type,
        autoflush=False,
        expire_on_commit=False,
    )


def test_project_cas_miss_rolls_back_new_revision_and_reports_safe_conflict(
    tmp_path: Path,
) -> None:
    initial = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        before = table_state(database.engine)
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER test_ignore_project_cas "
                "BEFORE UPDATE OF concurrency_version ON projects BEGIN "
                "SELECT RAISE(IGNORE); END"
            )
        try:
            with pytest.raises(ConcurrencyConflict) as captured:
                database.repository.append_revision(
                    initial.project.id,
                    ConcurrencyVersion(1),
                    ProjectTitle("CAS failure"),
                    ProjectDescription(),
                    clock=lambda: later(),
                    revision_id_factory=lambda: revision_id(50_002),
                )
            after = table_state(database.engine)
        finally:
            with database.engine.begin() as connection:
                connection.exec_driver_sql("DROP TRIGGER test_ignore_project_cas")

    assert captured.value.expected_version == 1
    assert captured.value.actual_version == 1
    assert after == before


def test_head_update_failure_rolls_back_revision_and_project_cas(tmp_path: Path) -> None:
    initial = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        before = table_state(database.engine)
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER test_fail_project_head_update "
                "BEFORE UPDATE ON project_heads BEGIN "
                "SELECT RAISE(ABORT, 'controlled head update failure'); END"
            )
        try:
            with pytest.raises(ProjectPersistenceConflict):
                database.repository.append_revision(
                    initial.project.id,
                    ConcurrencyVersion(1),
                    ProjectTitle("Head failure"),
                    ProjectDescription(),
                    clock=lambda: later(),
                    revision_id_factory=lambda: revision_id(60_002),
                )
            after = table_state(database.engine)
        finally:
            with database.engine.begin() as connection:
                connection.exec_driver_sql("DROP TRIGGER test_fail_project_head_update")

    assert after == before


def test_commit_failure_rolls_back_closes_session_and_hides_driver_details(
    tmp_path: Path,
) -> None:
    TrackingSession.instances.clear()
    initial = aggregate(title="Commit canary body")
    with repository_database(tmp_path) as database:
        factory = tracking_factory(database, CommitFailingSession)
        repository = SqlAlchemyProjectRepository(factory)
        with pytest.raises(ProjectRepositoryError) as captured:
            repository.create(initial)

        assert len(TrackingSession.instances) == 1
        failed_session = TrackingSession.instances[0]
        assert failed_session.rollback_called
        assert failed_session.close_called
        assert "COMMIT" not in str(captured.value)
        assert "Commit canary body" not in str(captured.value)
        assert database.repository.get(initial.project.id) is None
        assert table_state(database.engine)["projects"] == 0


def test_unexpected_create_failure_is_safely_converted_and_rolled_back(
    tmp_path: Path,
) -> None:
    TrackingSession.instances.clear()
    initial = aggregate()
    with repository_database(tmp_path) as database:
        repository = SqlAlchemyProjectRepository(
            tracking_factory(database, UnexpectedCommitFailureSession)
        )
        with pytest.raises(ProjectRepositoryError):
            repository.create(initial)

        assert TrackingSession.instances[0].rollback_called
        assert TrackingSession.instances[0].close_called
        assert table_state(database.engine)["projects"] == 0


def test_each_operation_uses_an_independent_session_and_closes_every_path(
    tmp_path: Path,
) -> None:
    TrackingSession.instances.clear()
    initial = aggregate()
    with repository_database(tmp_path) as database:
        repository = SqlAlchemyProjectRepository(tracking_factory(database))
        repository.create(initial)
        assert repository.get(initial.project.id) == initial
        assert repository.get(project_id(404)) is None
        repository.append_revision(
            initial.project.id,
            ConcurrencyVersion(1),
            ProjectTitle("Second"),
            ProjectDescription(),
            clock=lambda: later(),
            revision_id_factory=lambda: revision_id(70_002),
        )
        with pytest.raises(ConcurrencyConflict):
            repository.append_revision(
                initial.project.id,
                ConcurrencyVersion(1),
                ProjectTitle("Stale"),
                ProjectDescription(),
            )

        assert len(TrackingSession.instances) == 5
        assert len({id(session) for session in TrackingSession.instances}) == 5
        assert all(session.close_called for session in TrackingSession.instances)
        checked_out = getattr(database.engine.pool, "checkedout", lambda: 0)()
        assert checked_out == 0


def test_session_factory_failure_is_converted_without_database_access(tmp_path: Path) -> None:
    def broken_factory() -> Session:
        raise RuntimeError("D:/private/database.sqlite3 secret SQL")

    repository = SqlAlchemyProjectRepository(broken_factory)
    with pytest.raises(ProjectRepositoryError) as captured:
        repository.get(project_id(1))

    assert "private" not in str(captured.value)
    assert "SQL" not in str(captured.value)


@pytest.mark.parametrize(
    "failure",
    [OperationalError("SELECT", {}, sqlite3.OperationalError("failed")), RuntimeError("failed")],
    ids=("sqlalchemy", "unexpected"),
)
def test_get_converts_query_failures_and_closes_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    TrackingSession.instances.clear()
    with repository_database(tmp_path) as database:
        repository = SqlAlchemyProjectRepository(tracking_factory(database))

        def fail_load(_session: Session, _project_id: object) -> object:
            raise failure

        monkeypatch.setattr(repository, "_load_current", fail_load)
        with pytest.raises(ProjectRepositoryError):
            repository.get(project_id(1))

        assert TrackingSession.instances[0].rollback_called
        assert TrackingSession.instances[0].close_called


def test_append_sqlalchemy_and_unexpected_failures_are_safe_and_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        before = table_state(database.engine)

        def fail_begin(_session: Session) -> None:
            raise OperationalError("BEGIN", {}, sqlite3.OperationalError("locked canary"))

        monkeypatch.setattr(database.repository, "_begin_immediate", fail_begin)
        with pytest.raises(ProjectRepositoryError):
            database.repository.append_revision(
                initial.project.id,
                ConcurrencyVersion(1),
                ProjectTitle("SQLAlchemy failure"),
                ProjectDescription(),
            )
        monkeypatch.undo()

        def fail_id() -> object:
            raise RuntimeError("identifier factory canary")

        with pytest.raises(ProjectRepositoryError):
            database.repository.append_revision(
                initial.project.id,
                ConcurrencyVersion(1),
                ProjectTitle("Unexpected failure"),
                ProjectDescription(),
                clock=lambda: later(),
                revision_id_factory=fail_id,  # type: ignore[arg-type]
            )
        after = table_state(database.engine)

    assert after == before


def test_head_cas_zero_rows_rolls_back_and_becomes_persistence_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        before = table_state(database.engine)

        def miss_head(
            project_identifier: object,
            _expected_revision: object,
            new_revision: object,
            updated_at: object,
        ) -> object:
            return (
                update(ProjectHeadRecord)
                .where(
                    ProjectHeadRecord.project_id == project_identifier,
                    ProjectHeadRecord.revision_id == revision_id(999_999),
                )
                .values(revision_id=new_revision, updated_at=updated_at)
            )

        monkeypatch.setattr(repository_module, "head_compare_and_swap", miss_head)
        with pytest.raises(ProjectPersistenceConflict):
            database.repository.append_revision(
                initial.project.id,
                ConcurrencyVersion(1),
                ProjectTitle("Head CAS miss"),
                ProjectDescription(),
                clock=lambda: later(),
                revision_id_factory=lambda: revision_id(80_002),
            )
        after = table_state(database.engine)

    assert after == before


def test_project_cas_zero_rows_distinguishes_project_removed_after_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER test_ignore_project_cas_missing "
                "BEFORE UPDATE OF concurrency_version ON projects BEGIN "
                "SELECT RAISE(IGNORE); END"
            )
        monkeypatch.setattr(database.repository, "get", lambda _project_id: None)
        try:
            with pytest.raises(ProjectNotFound):
                database.repository.append_revision(
                    initial.project.id,
                    ConcurrencyVersion(1),
                    ProjectTitle("Project disappeared"),
                    ProjectDescription(),
                    clock=lambda: later(),
                    revision_id_factory=lambda: revision_id(90_002),
                )
        finally:
            with database.engine.begin() as connection:
                connection.exec_driver_sql("DROP TRIGGER test_ignore_project_cas_missing")


def test_head_cas_zero_rows_distinguishes_project_removed_after_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = aggregate()
    with repository_database(tmp_path) as database:
        database.repository.create(initial)

        def miss_head(
            project_identifier: object,
            _expected_revision: object,
            new_revision: object,
            updated_at: object,
        ) -> object:
            return (
                update(ProjectHeadRecord)
                .where(
                    ProjectHeadRecord.project_id == project_identifier,
                    ProjectHeadRecord.revision_id == revision_id(999_998),
                )
                .values(revision_id=new_revision, updated_at=updated_at)
            )

        monkeypatch.setattr(repository_module, "head_compare_and_swap", miss_head)
        monkeypatch.setattr(database.repository, "get", lambda _project_id: None)
        with pytest.raises(ProjectNotFound):
            database.repository.append_revision(
                initial.project.id,
                ConcurrencyVersion(1),
                ProjectTitle("Project disappeared at head CAS"),
                ProjectDescription(),
                clock=lambda: later(),
                revision_id_factory=lambda: revision_id(90_003),
            )
