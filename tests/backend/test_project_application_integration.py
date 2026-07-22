"""Project application use cases over migrated real transactional repositories."""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import event
from tests.backend.project_repository_support import (
    BASE_TIME,
    project_id,
    repository_database,
    revision_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.application.commands import (
    CreateProjectCommand,
    ReviseProjectCommand,
)
from aiwebnovel.project.application.models import ProjectSnapshot
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import (
    ProjectCommandService,
    ProjectQueryService,
)
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.errors import ProjectAlreadyExists, ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.repository import SqlAlchemyProjectRepository
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.integration


def _database_state(engine: object) -> dict[str, object]:
    with engine.connect() as connection:  # type: ignore[attr-defined]
        counts = {
            table: connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
            for table in ("projects", "project_revisions", "project_heads")
        }
        project_row = connection.exec_driver_sql("SELECT concurrency_version FROM projects").one()
        revision_row = connection.exec_driver_sql(
            "SELECT revision_number FROM project_revisions ORDER BY revision_number DESC LIMIT 1"
        ).one()
        head_row = connection.exec_driver_sql("SELECT revision_id FROM project_heads").one()
    return {
        **counts,
        "concurrency_version": project_row[0],
        "revision_number": revision_row[0],
        "head_revision_id": head_row[0],
    }


def test_real_create_query_revise_and_stale_flow_is_atomic(tmp_path: object) -> None:
    stale_clock_calls = 0
    stale_factory_calls = 0
    detached_snapshot: ProjectSnapshot
    with repository_database(tmp_path) as database:  # type: ignore[arg-type]
        revision_ids = iter((revision_id(1081), revision_id(2081)))
        command_service = ProjectCommandService(
            database.repository,
            clock=lambda: BASE_TIME,
            project_id_factory=lambda: project_id(81),
            revision_id_factory=lambda: next(revision_ids),
        )
        query_service = ProjectQueryService(database.repository)

        created = command_service.create_project(
            CreateProjectCommand("  Integration title  ", "Initial description")
        )
        assert _database_state(database.engine) == {
            "projects": 1,
            "project_revisions": 1,
            "project_heads": 1,
            "concurrency_version": 1,
            "revision_number": 1,
            "head_revision_id": str(revision_id(1081)),
        }

        queried = query_service.get_project(GetProjectQuery(created.project_id))
        assert queried == created

        revised = command_service.revise_project(
            ReviseProjectCommand(created.project_id, 1, "Revision two", "Complete replacement")
        )
        assert revised.revision_number == 2
        assert revised.concurrency_version == 2
        assert revised.current_revision_id == str(revision_id(2081))
        assert _database_state(database.engine) == {
            "projects": 1,
            "project_revisions": 2,
            "project_heads": 1,
            "concurrency_version": 2,
            "revision_number": 2,
            "head_revision_id": str(revision_id(2081)),
        }
        assert query_service.get_project(GetProjectQuery(created.project_id)) == revised

        def stale_clock() -> object:
            nonlocal stale_clock_calls
            stale_clock_calls += 1
            return BASE_TIME + timedelta(seconds=1)

        def stale_factory() -> ProjectRevisionId:
            nonlocal stale_factory_calls
            stale_factory_calls += 1
            return revision_id(3081)

        stale_service = ProjectCommandService(
            database.repository,
            clock=stale_clock,  # type: ignore[arg-type]
            revision_id_factory=stale_factory,
        )
        stale_command = ReviseProjectCommand(
            created.project_id,
            1,
            "CANARY-STALE-TITLE",
            "CANARY-STALE-DESCRIPTION",
        )
        with pytest.raises(ConcurrencyConflict) as raised:
            stale_service.revise_project(stale_command)

        assert raised.value.expected_version == 1
        assert raised.value.actual_version == 2
        assert stale_clock_calls == 0
        assert stale_factory_calls == 0
        assert _database_state(database.engine) == {
            "projects": 1,
            "project_revisions": 2,
            "project_heads": 1,
            "concurrency_version": 2,
            "revision_number": 2,
            "head_revision_id": str(revision_id(2081)),
        }
        detached_snapshot = revised

    assert detached_snapshot.title == "Revision two"
    assert detached_snapshot.description == "Complete replacement"


def test_real_missing_query_and_revise_have_no_generator_side_effect(tmp_path: object) -> None:
    clock_calls = 0
    factory_calls = 0
    with repository_database(tmp_path) as database:  # type: ignore[arg-type]
        missing_id = project_id(82)

        assert (
            ProjectQueryService(database.repository).get_project(GetProjectQuery(str(missing_id)))
            is None
        )

        def clock() -> object:
            nonlocal clock_calls
            clock_calls += 1
            return BASE_TIME

        def revision_factory() -> ProjectRevisionId:
            nonlocal factory_calls
            factory_calls += 1
            return revision_id(1082)

        service = ProjectCommandService(
            database.repository,
            clock=clock,  # type: ignore[arg-type]
            revision_id_factory=revision_factory,
        )
        with pytest.raises(ProjectNotFound) as raised:
            service.revise_project(ReviseProjectCommand(str(missing_id), 1, "Title"))

        assert raised.value.project_id == missing_id
        assert clock_calls == 0
        assert factory_calls == 0
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM projects").scalar_one() == 0


def test_application_commands_enter_one_write_transaction_and_query_enters_none(
    tmp_path: object,
) -> None:
    with repository_database(tmp_path) as database:  # type: ignore[arg-type]
        statements: list[str] = []

        def capture_statement(
            connection: object,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            statements.append(statement.strip().upper())

        event.listen(database.engine, "before_cursor_execute", capture_statement)
        try:
            service = ProjectCommandService(
                database.repository,
                clock=lambda: BASE_TIME,
                project_id_factory=lambda: project_id(83),
                revision_id_factory=lambda: revision_id(1083),
            )
            created = service.create_project(CreateProjectCommand("Title"))
            assert statements.count("BEGIN IMMEDIATE") == 1

            statements.clear()
            ProjectQueryService(database.repository).get_project(
                GetProjectQuery(created.project_id)
            )
            assert "BEGIN IMMEDIATE" not in statements
            assert sum(statement.startswith("SELECT ") for statement in statements) == 1

            statements.clear()
            revised_service = ProjectCommandService(
                database.repository,
                clock=lambda: BASE_TIME + timedelta(seconds=1),
                revision_id_factory=lambda: revision_id(2083),
            )
            revised_service.revise_project(
                ReviseProjectCommand(created.project_id, 1, "Revision two")
            )
            assert statements.count("BEGIN IMMEDIATE") == 1
            assert sum(statement.startswith("SELECT ") for statement in statements) == 1
        finally:
            event.remove(database.engine, "before_cursor_execute", capture_statement)


class BarrierRepository:
    """Test-only synchronization wrapper around one independent real repository."""

    def __init__(
        self,
        repository: SqlAlchemyProjectRepository,
        barrier: Barrier,
    ) -> None:
        self._repository = repository
        self._barrier = barrier

    def create(self, aggregate_value: ProjectAggregate) -> ProjectAggregate:
        return self._repository.create(aggregate_value)

    def get(self, identifier: ProjectId) -> ProjectAggregate | None:
        return self._repository.get(identifier)

    def append_revision(
        self,
        identifier: ProjectId,
        expected_version: ConcurrencyVersion,
        title: ProjectTitle,
        description: ProjectDescription,
        *,
        clock: Clock | None = None,
        revision_id_factory: Callable[[], ProjectRevisionId] = ProjectRevisionId.new,
    ) -> ProjectAggregate:
        self._barrier.wait()
        return self._repository.append_revision(
            identifier,
            expected_version,
            title,
            description,
            clock=clock,
            revision_id_factory=revision_id_factory,
        )


def test_two_application_services_concurrently_produce_one_success_and_one_conflict(
    tmp_path: object,
) -> None:
    with repository_database(tmp_path) as database:  # type: ignore[arg-type]
        initial_service = ProjectCommandService(
            database.repository,
            clock=lambda: BASE_TIME,
            project_id_factory=lambda: project_id(84),
            revision_id_factory=lambda: revision_id(1084),
        )
        initial = initial_service.create_project(CreateProjectCommand("Initial"))
        barrier = Barrier(2)
        repositories = (
            BarrierRepository(
                SqlAlchemyProjectRepository(database.session_factory),
                barrier,
            ),
            BarrierRepository(
                SqlAlchemyProjectRepository(database.session_factory),
                barrier,
            ),
        )
        services = (
            ProjectCommandService(
                repositories[0],
                clock=lambda: BASE_TIME + timedelta(seconds=1),
                revision_id_factory=lambda: revision_id(2084),
            ),
            ProjectCommandService(
                repositories[1],
                clock=lambda: BASE_TIME + timedelta(seconds=2),
                revision_id_factory=lambda: revision_id(3084),
            ),
        )
        commands = (
            ReviseProjectCommand(initial.project_id, 1, "Concurrent A", "Body A"),
            ReviseProjectCommand(initial.project_id, 1, "Concurrent B", "Body B"),
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures: tuple[Future[ProjectSnapshot], Future[ProjectSnapshot]] = (
                executor.submit(services[0].revise_project, commands[0]),
                executor.submit(services[1].revise_project, commands[1]),
            )
            successes: list[ProjectSnapshot] = []
            conflicts: list[ConcurrencyConflict] = []
            for future in futures:
                try:
                    successes.append(future.result())
                except ConcurrencyConflict as exc:
                    conflicts.append(exc)

        assert len(successes) == 1
        assert len(conflicts) == 1
        assert conflicts[0].expected_version == 1
        assert conflicts[0].actual_version == 2
        final = ProjectQueryService(database.repository).get_project(
            GetProjectQuery(initial.project_id)
        )
        assert final == successes[0]
        assert final is not None
        assert final.concurrency_version == 2
        assert final.revision_number == 2
        assert final.current_revision_id in {str(revision_id(2084)), str(revision_id(3084))}
        assert _database_state(database.engine)["project_revisions"] == 2
        assert commands == (
            ReviseProjectCommand(initial.project_id, 1, "Concurrent A", "Body A"),
            ReviseProjectCommand(initial.project_id, 1, "Concurrent B", "Body B"),
        )


def test_application_privacy_canary_appears_only_in_success_snapshot_and_not_logs(
    tmp_path: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    title = "CANARY-SUCCESS-TITLE-85"
    description = "CANARY-SUCCESS-DESCRIPTION-85"
    with repository_database(tmp_path) as database:  # type: ignore[arg-type]
        service = ProjectCommandService(
            database.repository,
            clock=lambda: BASE_TIME,
            project_id_factory=lambda: project_id(85),
            revision_id_factory=lambda: revision_id(1085),
        )
        snapshot = service.create_project(CreateProjectCommand(title, description))

        assert snapshot.title == title
        assert snapshot.description == description
        with pytest.raises(ProjectAlreadyExists) as raised:
            service.create_project(CreateProjectCommand(title, description))

        rendered_error = str(raised.value)
        assert title not in rendered_error
        assert description not in rendered_error
        assert "SELECT" not in rendered_error.upper()
        assert ".sqlite" not in rendered_error.lower()
        assert title not in caplog.text
        assert description not in caplog.text
