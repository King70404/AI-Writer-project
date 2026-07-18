"""Tests for immutable Project entities and aggregate relationships."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.identifiers import PrefixedUlid, Ulid
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.entities import Project, ProjectAggregate, ProjectHead, ProjectRevision
from aiwebnovel.project.errors import InvalidProjectState, ProjectRevisionConflict
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.unit

BASE_TIME = datetime(2026, 1, 2, 3, 4, 5, 678_000, tzinfo=UTC)


def _project_id(value: int = 1) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_int(value))


def _revision_id(value: int = 2) -> ProjectRevisionId:
    return ProjectRevisionId.from_ulid(Ulid.from_int(value))


def _project(project_id: ProjectId | None = None, *, updated_at: datetime = BASE_TIME) -> Project:
    return Project(
        id=_project_id() if project_id is None else project_id,
        concurrency_version=ConcurrencyVersion(),
        created_at=BASE_TIME,
        updated_at=updated_at,
    )


def _revision(
    project_id: ProjectId | None = None,
    revision_id: ProjectRevisionId | None = None,
    *,
    created_at: datetime = BASE_TIME,
) -> ProjectRevision:
    return ProjectRevision(
        id=_revision_id() if revision_id is None else revision_id,
        project_id=_project_id() if project_id is None else project_id,
        revision_number=RevisionNumber(),
        title=ProjectTitle("Title"),
        description=ProjectDescription("Description"),
        created_at=created_at,
    )


def _head(
    project_id: ProjectId | None = None,
    revision_id: ProjectRevisionId | None = None,
    *,
    updated_at: datetime = BASE_TIME,
) -> ProjectHead:
    return ProjectHead(
        project_id=_project_id() if project_id is None else project_id,
        revision_id=_revision_id() if revision_id is None else revision_id,
        updated_at=updated_at,
    )


def test_project_normalizes_aware_times_and_allows_later_concurrency_versions() -> None:
    source_timezone = timezone(timedelta(hours=8))
    created = datetime(2026, 1, 2, 11, 4, 5, tzinfo=source_timezone)
    updated = created + timedelta(seconds=1)
    project = Project(
        id=_project_id(),
        concurrency_version=ConcurrencyVersion(3),
        created_at=created,
        updated_at=updated,
    )

    assert project.created_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert project.updated_at == datetime(2026, 1, 2, 3, 4, 6, tzinfo=UTC)
    assert int(project.concurrency_version) == 3


def test_project_rejects_wrong_types_naive_time_and_reverse_time() -> None:
    with pytest.raises(InvalidProjectState):
        Project(_revision_id(), ConcurrencyVersion(), BASE_TIME, BASE_TIME)
    with pytest.raises(InvalidProjectState):
        Project(_project_id(), RevisionNumber(), BASE_TIME, BASE_TIME)
    with pytest.raises(InvalidProjectState):
        Project(_project_id(), ConcurrencyVersion(), datetime(2026, 1, 1), BASE_TIME)
    with pytest.raises(InvalidProjectState):
        Project(_project_id(), ConcurrencyVersion(), BASE_TIME, BASE_TIME - timedelta(seconds=1))


def test_project_revision_has_concrete_values_and_normalized_utc_time() -> None:
    local_time = BASE_TIME.astimezone(timezone(timedelta(hours=-5)))
    revision = _revision(created_at=local_time)

    assert type(revision.id) is ProjectRevisionId
    assert type(revision.project_id) is ProjectId
    assert revision.created_at == BASE_TIME
    assert not hasattr(revision, "updated_at")
    assert not hasattr(revision, "concurrency_version")
    assert not hasattr(revision, "is_current")


@pytest.mark.parametrize(
    "replacement",
    [
        {"id": _project_id()},
        {"project_id": _revision_id()},
        {"revision_number": ConcurrencyVersion()},
        {"title": "raw title"},
        {"description": "raw description"},
        {"created_at": datetime(2026, 1, 1)},
    ],
)
def test_project_revision_rejects_wrong_field_types(replacement: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "id": _revision_id(),
        "project_id": _project_id(),
        "revision_number": RevisionNumber(),
        "title": ProjectTitle("Title"),
        "description": ProjectDescription("Description"),
        "created_at": BASE_TIME,
    }
    arguments.update(replacement)

    with pytest.raises(InvalidProjectState):
        ProjectRevision(**arguments)


def test_project_head_validates_concrete_ids_and_utc_time() -> None:
    local_time = BASE_TIME.astimezone(timezone(timedelta(hours=9)))
    head = _head(updated_at=local_time)

    assert head.updated_at == BASE_TIME
    with pytest.raises(InvalidProjectState):
        ProjectHead(_revision_id(), _revision_id(), BASE_TIME)
    with pytest.raises(InvalidProjectState):
        ProjectHead(_project_id(), _project_id(), BASE_TIME)
    with pytest.raises(InvalidProjectState):
        ProjectHead(_project_id(), _revision_id(), datetime(2026, 1, 1))


def test_project_aggregate_accepts_one_consistent_current_revision() -> None:
    project_id = _project_id()
    revision_id = _revision_id()
    aggregate = ProjectAggregate(
        project=_project(project_id),
        head=_head(project_id, revision_id),
        current_revision=_revision(project_id, revision_id),
    )

    assert aggregate.project.id == aggregate.head.project_id
    assert aggregate.current_revision.project_id == aggregate.project.id
    assert aggregate.head.revision_id == aggregate.current_revision.id


def test_project_aggregate_rejects_wrong_objects_and_relationships() -> None:
    project_id = _project_id()
    revision_id = _revision_id()
    project = _project(project_id)
    revision = _revision(project_id, revision_id)
    head = _head(project_id, revision_id)

    with pytest.raises(InvalidProjectState):
        ProjectAggregate("project", head, revision)
    with pytest.raises(InvalidProjectState):
        ProjectAggregate(project, _head(_project_id(8), revision_id), revision)
    with pytest.raises(InvalidProjectState):
        ProjectAggregate(project, head, _revision(_project_id(8), revision_id))
    with pytest.raises(InvalidProjectState):
        ProjectAggregate(project, _head(project_id, _revision_id(9)), revision)
    with pytest.raises(InvalidProjectState):
        ProjectAggregate(
            _project(project_id),
            _head(project_id, revision_id, updated_at=BASE_TIME),
            _revision(project_id, revision_id, created_at=BASE_TIME + timedelta(seconds=1)),
        )


def test_project_entities_and_aggregate_are_immutable() -> None:
    project_id = _project_id()
    revision_id = _revision_id()
    project = _project(project_id)
    revision = _revision(project_id, revision_id)
    head = _head(project_id, revision_id)
    aggregate = ProjectAggregate(project, head, revision)

    with pytest.raises(FrozenInstanceError):
        project.updated_at = BASE_TIME + timedelta(seconds=1)
    with pytest.raises(FrozenInstanceError):
        revision.title = ProjectTitle("Changed")
    with pytest.raises(FrozenInstanceError):
        head.revision_id = _revision_id(4)
    with pytest.raises(FrozenInstanceError):
        aggregate.current_revision = _revision(project_id, _revision_id(4))


def test_project_revision_conflict_has_safe_integer_fields() -> None:
    conflict = ProjectRevisionConflict(expected_revision_number=2, actual_revision_number=3)

    assert conflict.expected_revision_number == 2
    assert conflict.actual_revision_number == 3
    assert str(conflict) == "The expected Project revision does not match the current revision."
    with pytest.raises(InvalidProjectState):
        ProjectRevisionConflict(expected_revision_number=0, actual_revision_number=3)


def test_generic_prefixed_id_cannot_enter_project_entities() -> None:
    generic_project_id = PrefixedUlid("prj", Ulid.from_int(1))

    with pytest.raises(InvalidProjectState):
        Project(generic_project_id, ConcurrencyVersion(), BASE_TIME, BASE_TIME)
