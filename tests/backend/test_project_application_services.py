"""Project application service conversion, mapping, and error propagation."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from tests.backend.project_repository_support import BASE_TIME, aggregate, project_id, revision_id

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.application.commands import (
    CreateProjectCommand,
    ReviseProjectCommand,
)
from aiwebnovel.project.application.models import ProjectSnapshot
from aiwebnovel.project.application.services import ProjectCommandService
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.errors import (
    ProjectAlreadyExists,
    ProjectDataCorruption,
    ProjectNotFound,
    ProjectRepositoryError,
)
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.transitions import create_next_project_revision
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.unit


class CommandSpyRepository:
    def __init__(self) -> None:
        self.create_calls: list[ProjectAggregate] = []
        self.append_calls: list[
            tuple[
                ProjectId,
                ConcurrencyVersion,
                ProjectTitle,
                ProjectDescription,
                Clock | None,
                Callable[[], ProjectRevisionId],
            ]
        ] = []
        self.get_calls: list[ProjectId] = []
        self.create_result: ProjectAggregate | None = None
        self.append_result: ProjectAggregate | None = None
        self.create_error: Exception | None = None
        self.append_error: Exception | None = None

    def create(self, aggregate_value: ProjectAggregate) -> ProjectAggregate:
        self.create_calls.append(aggregate_value)
        if self.create_error is not None:
            raise self.create_error
        return self.create_result or aggregate_value

    def get(self, identifier: ProjectId) -> ProjectAggregate | None:
        self.get_calls.append(identifier)
        return None

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
        self.append_calls.append(
            (identifier, expected_version, title, description, clock, revision_id_factory)
        )
        if self.append_error is not None:
            raise self.append_error
        if self.append_result is None:
            raise AssertionError("append_result is required for a successful spy append")
        return self.append_result


def test_create_service_normalizes_values_calls_create_once_and_maps_result() -> None:
    repository = CommandSpyRepository()

    def clock() -> datetime:
        return BASE_TIME

    def project_factory() -> ProjectId:
        return project_id(61)

    def revision_factory() -> ProjectRevisionId:
        return revision_id(1061)

    service = ProjectCommandService(
        repository,
        clock=clock,
        project_id_factory=project_factory,
        revision_id_factory=revision_factory,
    )
    command = CreateProjectCommand("  Normalized title  ", "line one\r\nline two")

    snapshot = service.create_project(command)

    assert isinstance(snapshot, ProjectSnapshot)
    assert snapshot.title == "Normalized title"
    assert snapshot.description == "line one\nline two"
    assert snapshot.project_id == str(project_id(61))
    assert snapshot.current_revision_id == str(revision_id(1061))
    assert snapshot.revision_number == 1
    assert snapshot.concurrency_version == 1
    assert len(repository.create_calls) == 1
    assert repository.get_calls == []
    assert repository.append_calls == []
    assert command == CreateProjectCommand("  Normalized title  ", "line one\r\nline two")


def test_create_service_allows_empty_description() -> None:
    repository = CommandSpyRepository()
    service = ProjectCommandService(
        repository,
        clock=lambda: BASE_TIME,
        project_id_factory=lambda: project_id(62),
        revision_id_factory=lambda: revision_id(1062),
    )

    snapshot = service.create_project(CreateProjectCommand("Title"))

    assert snapshot.description == ""


def test_create_service_maps_repository_return_value_not_uncommitted_input() -> None:
    repository = CommandSpyRepository()
    repository.create_result = aggregate(64, title="Repository result")
    service = ProjectCommandService(
        repository,
        clock=lambda: BASE_TIME,
        project_id_factory=lambda: project_id(63),
        revision_id_factory=lambda: revision_id(1063),
    )

    snapshot = service.create_project(CreateProjectCommand("Input title"))

    assert snapshot.project_id == str(project_id(64))
    assert snapshot.title == "Repository result"
    assert len(repository.create_calls) == 1
    assert repository.create_calls[0].project.id == project_id(63)


@pytest.mark.parametrize(
    "error",
    [ProjectAlreadyExists(project_id(65)), ProjectRepositoryError()],
)
def test_create_service_propagates_repository_error_unchanged(error: Exception) -> None:
    repository = CommandSpyRepository()
    repository.create_error = error
    service = ProjectCommandService(
        repository,
        clock=lambda: BASE_TIME,
        project_id_factory=lambda: project_id(65),
        revision_id_factory=lambda: revision_id(1065),
    )

    with pytest.raises(type(error)) as raised:
        service.create_project(CreateProjectCommand("Title"))

    assert raised.value is error
    assert len(repository.create_calls) == 1


def test_revise_service_converts_all_values_passes_dependencies_and_maps_result() -> None:
    current = aggregate(66)
    next_time = BASE_TIME + timedelta(seconds=1)
    revised = create_next_project_revision(
        current,
        ConcurrencyVersion(1),
        "Replacement",
        "Replacement description",
        clock=lambda: next_time,
        revision_id_factory=lambda: revision_id(2066),
    )
    repository = CommandSpyRepository()
    repository.append_result = revised

    def clock() -> datetime:
        return next_time

    def revision_factory() -> ProjectRevisionId:
        return revision_id(2066)

    service = ProjectCommandService(
        repository,
        clock=clock,
        project_id_factory=lambda: project_id(9999),
        revision_id_factory=revision_factory,
    )
    command = ReviseProjectCommand(
        str(current.project.id),
        1,
        "  Replacement  ",
        "Replacement description",
    )

    snapshot = service.revise_project(command)

    assert snapshot.title == "Replacement"
    assert snapshot.revision_number == 2
    assert snapshot.concurrency_version == 2
    assert repository.get_calls == []
    assert repository.create_calls == []
    assert len(repository.append_calls) == 1
    identifier, version, title, description, passed_clock, passed_factory = repository.append_calls[
        0
    ]
    assert type(identifier) is ProjectId
    assert identifier == current.project.id
    assert type(version) is ConcurrencyVersion
    assert int(version) == 1
    assert type(title) is ProjectTitle
    assert str(title) == "Replacement"
    assert type(description) is ProjectDescription
    assert str(description) == "Replacement description"
    assert passed_clock is clock
    assert passed_factory is revision_factory
    assert command.title == "  Replacement  "


@pytest.mark.parametrize(
    "error",
    [
        ProjectNotFound(project_id(67)),
        ProjectDataCorruption(),
        ProjectRepositoryError(),
    ],
)
def test_revise_service_propagates_repository_errors_unchanged(error: Exception) -> None:
    repository = CommandSpyRepository()
    repository.append_error = error
    service = ProjectCommandService(repository)

    with pytest.raises(type(error)) as raised:
        service.revise_project(ReviseProjectCommand(str(project_id(67)), 1, "Title"))

    assert raised.value is error
    assert len(repository.append_calls) == 1


def test_revise_service_preserves_concurrency_conflict_fields_and_body_privacy() -> None:
    error = ConcurrencyConflict(expected_version=1, actual_version=2)
    repository = CommandSpyRepository()
    repository.append_error = error
    command = ReviseProjectCommand(
        str(project_id(68)),
        1,
        "CANARY-TITLE-68",
        "CANARY-DESCRIPTION-68",
    )

    with pytest.raises(ConcurrencyConflict) as raised:
        ProjectCommandService(repository).revise_project(command)

    assert raised.value is error
    assert raised.value.expected_version == 1
    assert raised.value.actual_version == 2
    assert "CANARY" not in str(raised.value)


class ReprTrap:
    def __repr__(self) -> str:
        raise AssertionError("command type validation must not call repr")


@pytest.mark.parametrize("method_name", ["create_project", "revise_project"])
def test_command_service_rejects_wrong_type_without_repr_or_repository_access(
    method_name: str,
) -> None:
    repository = CommandSpyRepository()
    service = ProjectCommandService(repository)
    method = getattr(service, method_name)

    with pytest.raises(TypeError, match=r"command must be a .*ProjectCommand") as raised:
        method(ReprTrap())

    assert "ReprTrap" not in str(raised.value)
    assert repository.create_calls == []
    assert repository.append_calls == []
    assert repository.get_calls == []


def test_default_service_dependencies_produce_utc_snapshot() -> None:
    repository = CommandSpyRepository()

    snapshot = ProjectCommandService(repository).create_project(CreateProjectCommand("Title"))

    assert snapshot.created_at.tzinfo is UTC
    assert snapshot.created_at <= datetime.now(UTC)
