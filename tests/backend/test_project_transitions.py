"""Tests for pure deterministic Project aggregate transitions."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidConcurrencyVersion
from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.errors import InvalidProjectState, InvalidProjectTitle
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.transitions import create_initial_project, create_next_project_revision

pytestmark = pytest.mark.unit

INITIAL_TIME = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)


def _project_id(value: int = 100) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_int(value))


def _revision_id(value: int = 200) -> ProjectRevisionId:
    return ProjectRevisionId.from_ulid(Ulid.from_int(value))


def _initial_aggregate() -> ProjectAggregate:
    return create_initial_project(
        "Initial",
        "Description",
        clock=lambda: INITIAL_TIME,
        project_id_factory=lambda: _project_id(),
        revision_id_factory=lambda: _revision_id(),
    )


def test_initial_project_uses_one_time_and_deterministic_factories() -> None:
    clock_calls = 0
    project_calls = 0
    revision_calls = 0

    def clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        return INITIAL_TIME.astimezone(timezone(timedelta(hours=8)))

    def project_factory() -> ProjectId:
        nonlocal project_calls
        project_calls += 1
        return _project_id()

    def revision_factory() -> ProjectRevisionId:
        nonlocal revision_calls
        revision_calls += 1
        return _revision_id()

    aggregate = create_initial_project(
        "  Initial Project  ",
        "first\r\nsecond",
        clock=clock,
        project_id_factory=project_factory,
        revision_id_factory=revision_factory,
    )

    assert (clock_calls, project_calls, revision_calls) == (1, 1, 1)
    assert aggregate.project.id == aggregate.current_revision.project_id
    assert aggregate.head.project_id == aggregate.project.id
    assert aggregate.head.revision_id == aggregate.current_revision.id
    assert int(aggregate.project.concurrency_version) == 1
    assert int(aggregate.current_revision.revision_number) == 1
    assert str(aggregate.current_revision.title) == "Initial Project"
    assert str(aggregate.current_revision.description) == "first\nsecond"
    assert {
        aggregate.project.created_at,
        aggregate.project.updated_at,
        aggregate.current_revision.created_at,
        aggregate.head.updated_at,
    } == {INITIAL_TIME}


def test_initial_project_rejects_invalid_factory_types_and_clock() -> None:
    with pytest.raises(InvalidProjectState):
        create_initial_project(
            "Title",
            "",
            clock=lambda: INITIAL_TIME,
            project_id_factory=lambda: _revision_id(),
            revision_id_factory=lambda: _revision_id(),
        )
    with pytest.raises(InvalidProjectState):
        create_initial_project(
            "Title",
            "",
            clock=lambda: INITIAL_TIME,
            project_id_factory=lambda: _project_id(),
            revision_id_factory=lambda: _project_id(),
        )
    with pytest.raises(InvalidProjectState):
        create_initial_project(
            "Title",
            "",
            clock=lambda: datetime(2026, 1, 1),
            project_id_factory=lambda: _project_id(),
            revision_id_factory=lambda: _revision_id(),
        )


def test_initial_project_default_factories_return_concrete_business_ids() -> None:
    aggregate = create_initial_project("Title", "", clock=lambda: INITIAL_TIME)

    assert type(aggregate.project.id) is ProjectId
    assert type(aggregate.current_revision.id) is ProjectRevisionId


def test_next_revision_returns_new_aggregate_and_keeps_old_objects_unchanged() -> None:
    original = _initial_aggregate()
    original_project = original.project
    original_revision = original.current_revision
    original_head = original.head
    next_time = INITIAL_TIME + timedelta(minutes=1)

    updated = create_next_project_revision(
        original,
        ConcurrencyVersion(1),
        "Revised",
        "New description",
        clock=lambda: next_time,
        revision_id_factory=lambda: _revision_id(201),
    )

    assert updated is not original
    assert updated.project.id == original.project.id
    assert int(updated.project.concurrency_version) == 2
    assert updated.project.created_at == original.project.created_at
    assert updated.project.updated_at == next_time
    assert int(updated.current_revision.revision_number) == 2
    assert updated.current_revision.id == _revision_id(201)
    assert updated.head.revision_id == updated.current_revision.id
    assert updated.head.updated_at == updated.current_revision.created_at == next_time
    assert original.project is original_project
    assert original.current_revision is original_revision
    assert original.head is original_head
    assert int(original.project.concurrency_version) == 1
    assert int(original.current_revision.revision_number) == 1
    assert str(original.current_revision.title) == "Initial"


def test_stale_version_fails_before_values_clock_or_id_factory() -> None:
    aggregate = _initial_aggregate()
    clock_called = False
    factory_called = False

    def forbidden_clock() -> datetime:
        nonlocal clock_called
        clock_called = True
        raise AssertionError("clock must not be called for a stale transition")

    def forbidden_factory() -> ProjectRevisionId:
        nonlocal factory_called
        factory_called = True
        raise AssertionError("ID factory must not be called for a stale transition")

    with pytest.raises(ConcurrencyConflict) as captured:
        create_next_project_revision(
            aggregate,
            ConcurrencyVersion(2),
            "bad\ntitle",
            "",
            clock=forbidden_clock,
            revision_id_factory=forbidden_factory,
        )

    assert captured.value.expected_version == 2
    assert captured.value.actual_version == 1
    assert clock_called is False
    assert factory_called is False


def test_next_revision_rejects_clock_rollback_before_allocating_an_id() -> None:
    aggregate = _initial_aggregate()
    factory_calls = 0

    def factory() -> ProjectRevisionId:
        nonlocal factory_calls
        factory_calls += 1
        return _revision_id(201)

    with pytest.raises(InvalidProjectState):
        create_next_project_revision(
            aggregate,
            ConcurrencyVersion(),
            "Revised",
            "",
            clock=lambda: INITIAL_TIME - timedelta(microseconds=1),
            revision_id_factory=factory,
        )

    assert factory_calls == 0
    assert int(aggregate.project.concurrency_version) == 1
    assert aggregate.head.revision_id == _revision_id()


def test_next_revision_allows_equal_time_but_requires_a_new_exact_revision_id() -> None:
    aggregate = _initial_aggregate()
    updated = create_next_project_revision(
        aggregate,
        ConcurrencyVersion(),
        "Revised",
        "",
        clock=lambda: INITIAL_TIME,
        revision_id_factory=lambda: _revision_id(201),
    )

    assert updated.project.updated_at == INITIAL_TIME
    with pytest.raises(InvalidProjectState):
        create_next_project_revision(
            aggregate,
            ConcurrencyVersion(),
            "Revised",
            "",
            clock=lambda: INITIAL_TIME,
            revision_id_factory=lambda: aggregate.current_revision.id,
        )
    with pytest.raises(InvalidProjectState):
        create_next_project_revision(
            aggregate,
            ConcurrencyVersion(),
            "Revised",
            "",
            clock=lambda: INITIAL_TIME,
            revision_id_factory=lambda: _project_id(),
        )


def test_next_revision_rejects_invalid_aggregate_version_and_title() -> None:
    aggregate = _initial_aggregate()

    with pytest.raises(InvalidProjectState):
        create_next_project_revision(
            "aggregate",
            ConcurrencyVersion(),
            "Title",
            "",
            clock=lambda: INITIAL_TIME,
            revision_id_factory=lambda: _revision_id(201),
        )
    with pytest.raises(InvalidConcurrencyVersion):
        create_next_project_revision(
            aggregate,
            1,
            "Title",
            "",
            clock=lambda: INITIAL_TIME,
            revision_id_factory=lambda: _revision_id(201),
        )
    with pytest.raises(InvalidProjectTitle):
        create_next_project_revision(
            aggregate,
            ConcurrencyVersion(),
            "bad\ntitle",
            "",
            clock=lambda: INITIAL_TIME,
            revision_id_factory=lambda: _revision_id(201),
        )


def test_transition_functions_do_not_require_database_callbacks() -> None:
    def clock() -> datetime:
        return INITIAL_TIME

    aggregate = create_initial_project(
        "Title",
        "Description",
        clock=clock,
        project_id_factory=lambda: _project_id(),
        revision_id_factory=lambda: _revision_id(),
    )

    assert isinstance(aggregate, ProjectAggregate)
