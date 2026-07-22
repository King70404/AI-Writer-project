"""Deterministic Project command side-effect order and failure isolation."""

from collections.abc import Callable

import pytest
from tests.backend.project_repository_support import BASE_TIME, project_id, revision_id

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import InvalidConcurrencyVersion, InvalidDomainIdentifier
from aiwebnovel.project.application.commands import (
    CreateProjectCommand,
    ReviseProjectCommand,
)
from aiwebnovel.project.application.services import ProjectCommandService
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.errors import (
    InvalidProjectDescription,
    InvalidProjectTitle,
    ProjectRepositoryError,
)
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.unit


class OrderedRepository:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.create_calls = 0
        self.append_calls = 0
        self.get_calls = 0

    def create(self, aggregate_value: ProjectAggregate) -> ProjectAggregate:
        self.events.append("repository.create")
        self.create_calls += 1
        return aggregate_value

    def get(self, identifier: ProjectId) -> ProjectAggregate | None:
        self.events.append("repository.get")
        self.get_calls += 1
        return None

    def append_revision(
        self,
        identifier: ProjectId,
        expected_version: ConcurrencyVersion,
        title: ProjectTitle,
        description: ProjectDescription,
        *,
        clock: Callable[[], object] | None = None,
        revision_id_factory: Callable[[], ProjectRevisionId] = ProjectRevisionId.new,
    ) -> ProjectAggregate:
        self.events.append("repository.append_revision")
        self.append_calls += 1
        raise ProjectRepositoryError


def _tracked_service(
    events: list[str],
    repository: OrderedRepository,
    *,
    clock_error: Exception | None = None,
    project_error: Exception | None = None,
    revision_error: Exception | None = None,
) -> ProjectCommandService:
    def clock() -> object:
        events.append("clock")
        if clock_error is not None:
            raise clock_error
        return BASE_TIME

    def project_factory() -> ProjectId:
        events.append("project_id")
        if project_error is not None:
            raise project_error
        return project_id(71)

    def revision_factory() -> ProjectRevisionId:
        events.append("revision_id")
        if revision_error is not None:
            raise revision_error
        return revision_id(1071)

    return ProjectCommandService(
        repository,
        clock=clock,  # type: ignore[arg-type]
        project_id_factory=project_factory,
        revision_id_factory=revision_factory,
    )


def test_create_side_effect_order_and_exact_call_counts() -> None:
    events: list[str] = []
    repository = OrderedRepository(events)

    snapshot = _tracked_service(events, repository).create_project(
        CreateProjectCommand("Title", "Description")
    )

    assert events == ["clock", "project_id", "revision_id", "repository.create"]
    assert repository.create_calls == 1
    assert repository.get_calls == 0
    assert repository.append_calls == 0
    assert snapshot.project_id == str(project_id(71))


@pytest.mark.parametrize(
    ("command", "error_type"),
    [
        (CreateProjectCommand("   ", "Description"), InvalidProjectTitle),
        (CreateProjectCommand("Title", "x" * 2001), InvalidProjectDescription),
    ],
)
def test_invalid_create_values_have_no_observable_side_effects(
    command: CreateProjectCommand,
    error_type: type[Exception],
) -> None:
    events: list[str] = []
    repository = OrderedRepository(events)

    with pytest.raises(error_type):
        _tracked_service(events, repository).create_project(command)

    assert events == []
    assert repository.create_calls == 0


@pytest.mark.parametrize(
    ("failure", "expected_events"),
    [
        ("clock", ["clock"]),
        ("project", ["clock", "project_id"]),
        ("revision", ["clock", "project_id", "revision_id"]),
    ],
)
def test_create_dependency_failure_stops_later_side_effects(
    failure: str,
    expected_events: list[str],
) -> None:
    events: list[str] = []
    repository = OrderedRepository(events)
    errors = {
        "clock_error": RuntimeError("clock failed") if failure == "clock" else None,
        "project_error": RuntimeError("project ID failed") if failure == "project" else None,
        "revision_error": RuntimeError("revision ID failed") if failure == "revision" else None,
    }

    with pytest.raises(RuntimeError):
        _tracked_service(events, repository, **errors).create_project(CreateProjectCommand("Title"))

    assert events == expected_events
    assert repository.create_calls == 0


@pytest.mark.parametrize(
    ("command", "error_type"),
    [
        (ReviseProjectCommand("invalid", 1, "Title"), InvalidDomainIdentifier),
        (ReviseProjectCommand(str(project_id(72)), 0, "Title"), InvalidConcurrencyVersion),
        (ReviseProjectCommand(str(project_id(72)), True, "Title"), InvalidConcurrencyVersion),
        (ReviseProjectCommand(str(project_id(72)), 1.5, "Title"), InvalidConcurrencyVersion),
        (ReviseProjectCommand(str(project_id(72)), 1, "   "), InvalidProjectTitle),
        (
            ReviseProjectCommand(str(project_id(72)), 1, "Title", "x" * 2001),
            InvalidProjectDescription,
        ),
    ],
)
def test_invalid_revise_input_never_calls_repository_clock_or_revision_factory(
    command: ReviseProjectCommand,
    error_type: type[Exception],
) -> None:
    events: list[str] = []
    repository = OrderedRepository(events)

    with pytest.raises(error_type):
        _tracked_service(events, repository).revise_project(command)

    assert events == []
    assert repository.get_calls == 0
    assert repository.append_calls == 0


def test_valid_revise_calls_only_append_and_does_not_preinvoke_dependencies() -> None:
    events: list[str] = []
    repository = OrderedRepository(events)

    with pytest.raises(ProjectRepositoryError):
        _tracked_service(events, repository).revise_project(
            ReviseProjectCommand(str(project_id(73)), 1, "Title", "Description")
        )

    assert events == ["repository.append_revision"]
    assert repository.get_calls == 0
    assert repository.create_calls == 0
    assert repository.append_calls == 1
