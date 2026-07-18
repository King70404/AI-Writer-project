"""Pure Project aggregate creation and immutable revision transitions."""

from collections.abc import Callable
from datetime import datetime

from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import Clock, utc_now
from aiwebnovel.project.entities import Project, ProjectAggregate, ProjectHead, ProjectRevision
from aiwebnovel.project.errors import InvalidProjectState
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

ProjectIdFactory = Callable[[], ProjectId]
ProjectRevisionIdFactory = Callable[[], ProjectRevisionId]


def _new_project_id() -> ProjectId:
    return ProjectId.new()


def _new_project_revision_id() -> ProjectRevisionId:
    return ProjectRevisionId.new()


def _current_time(clock: Clock | None) -> datetime:
    try:
        return utc_now(clock)
    except (TypeError, ValueError):
        raise InvalidProjectState from None


def create_initial_project(
    title: str,
    description: str,
    *,
    clock: Clock | None = None,
    project_id_factory: ProjectIdFactory = _new_project_id,
    revision_id_factory: ProjectRevisionIdFactory = _new_project_revision_id,
) -> ProjectAggregate:
    """Create a valid initial aggregate without persistence or side effects."""
    project_title = ProjectTitle(title)
    project_description = ProjectDescription(description)
    now = _current_time(clock)
    project_id = project_id_factory()
    revision_id = revision_id_factory()
    if type(project_id) is not ProjectId or type(revision_id) is not ProjectRevisionId:
        raise InvalidProjectState

    project = Project(
        id=project_id,
        concurrency_version=ConcurrencyVersion(),
        created_at=now,
        updated_at=now,
    )
    revision = ProjectRevision(
        id=revision_id,
        project_id=project_id,
        revision_number=RevisionNumber(),
        title=project_title,
        description=project_description,
        created_at=now,
    )
    head = ProjectHead(project_id=project_id, revision_id=revision_id, updated_at=now)
    return ProjectAggregate(project=project, head=head, current_revision=revision)


def create_next_project_revision(
    aggregate: ProjectAggregate,
    expected_concurrency_version: ConcurrencyVersion,
    title: str,
    description: str,
    *,
    clock: Clock | None = None,
    revision_id_factory: ProjectRevisionIdFactory = _new_project_revision_id,
) -> ProjectAggregate:
    """Append a revision in memory, rejecting stale versions and clock rollback."""
    if type(aggregate) is not ProjectAggregate:
        raise InvalidProjectState
    assert_expected_version(
        actual=aggregate.project.concurrency_version,
        expected=expected_concurrency_version,
    )

    project_title = ProjectTitle(title)
    project_description = ProjectDescription(description)
    now = _current_time(clock)
    earliest_time = max(
        aggregate.project.updated_at,
        aggregate.current_revision.created_at,
        aggregate.head.updated_at,
    )
    if now < earliest_time:
        raise InvalidProjectState

    revision_id = revision_id_factory()
    if type(revision_id) is not ProjectRevisionId or revision_id == aggregate.current_revision.id:
        raise InvalidProjectState

    project = Project(
        id=aggregate.project.id,
        concurrency_version=aggregate.project.concurrency_version.next(),
        created_at=aggregate.project.created_at,
        updated_at=now,
    )
    revision = ProjectRevision(
        id=revision_id,
        project_id=aggregate.project.id,
        revision_number=aggregate.current_revision.revision_number.next(),
        title=project_title,
        description=project_description,
        created_at=now,
    )
    head = ProjectHead(
        project_id=aggregate.project.id,
        revision_id=revision_id,
        updated_at=now,
    )
    return ProjectAggregate(project=project, head=head, current_revision=revision)
