"""Explicit side-effect-free mappings between Project domain values and records."""

from aiwebnovel.project.entities import Project, ProjectAggregate, ProjectHead, ProjectRevision
from aiwebnovel.project.errors import InvalidProjectState
from aiwebnovel.project.persistence.models import (
    ProjectHeadRecord,
    ProjectRecord,
    ProjectRevisionRecord,
)
from aiwebnovel.project.values import ProjectDescription, ProjectTitle


def project_to_record(project: Project) -> ProjectRecord:
    """Copy one validated stable Project into a transient persistence record."""
    if type(project) is not Project:
        raise InvalidProjectState
    return ProjectRecord(
        id=project.id,
        concurrency_version=project.concurrency_version,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def project_from_record(record: ProjectRecord) -> Project:
    """Restore one stable Project without retaining SQLAlchemy state."""
    if type(record) is not ProjectRecord:
        raise InvalidProjectState
    return Project(
        id=record.id,
        concurrency_version=record.concurrency_version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def project_revision_to_record(revision: ProjectRevision) -> ProjectRevisionRecord:
    """Copy one immutable revision into a transient persistence record."""
    if type(revision) is not ProjectRevision:
        raise InvalidProjectState
    return ProjectRevisionRecord(
        id=revision.id,
        project_id=revision.project_id,
        revision_number=revision.revision_number,
        title=str(revision.title),
        description=str(revision.description),
        created_at=revision.created_at,
    )


def project_revision_from_record(record: ProjectRevisionRecord) -> ProjectRevision:
    """Restore an immutable revision and reapply Project value validation."""
    if type(record) is not ProjectRevisionRecord:
        raise InvalidProjectState
    return ProjectRevision(
        id=record.id,
        project_id=record.project_id,
        revision_number=record.revision_number,
        title=ProjectTitle(record.title),
        description=ProjectDescription(record.description),
        created_at=record.created_at,
    )


def project_head_to_record(head: ProjectHead) -> ProjectHeadRecord:
    """Copy one current-revision pointer into a transient record."""
    if type(head) is not ProjectHead:
        raise InvalidProjectState
    return ProjectHeadRecord(
        project_id=head.project_id,
        revision_id=head.revision_id,
        updated_at=head.updated_at,
    )


def project_head_from_record(record: ProjectHeadRecord) -> ProjectHead:
    """Restore one current-revision pointer without querying a database."""
    if type(record) is not ProjectHeadRecord:
        raise InvalidProjectState
    return ProjectHead(
        project_id=record.project_id,
        revision_id=record.revision_id,
        updated_at=record.updated_at,
    )


def project_aggregate_to_records(
    aggregate: ProjectAggregate,
) -> tuple[ProjectRecord, ProjectHeadRecord, ProjectRevisionRecord]:
    """Map a consistent aggregate to its three transient records."""
    if type(aggregate) is not ProjectAggregate:
        raise InvalidProjectState
    return (
        project_to_record(aggregate.project),
        project_head_to_record(aggregate.head),
        project_revision_to_record(aggregate.current_revision),
    )


def project_aggregate_from_records(
    project_record: ProjectRecord,
    head_record: ProjectHeadRecord,
    revision_record: ProjectRevisionRecord,
) -> ProjectAggregate:
    """Restore and validate one aggregate without database access."""
    return ProjectAggregate(
        project=project_from_record(project_record),
        head=project_head_from_record(head_record),
        current_revision=project_revision_from_record(revision_record),
    )


__all__ = [
    "project_aggregate_from_records",
    "project_aggregate_to_records",
    "project_from_record",
    "project_head_from_record",
    "project_head_to_record",
    "project_revision_from_record",
    "project_revision_to_record",
    "project_to_record",
]
