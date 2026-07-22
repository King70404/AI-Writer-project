"""Explicit mapping from the Project aggregate to its detached read model."""

from aiwebnovel.project.application.models import ProjectSnapshot
from aiwebnovel.project.entities import ProjectAggregate


def project_snapshot_from_aggregate(aggregate: ProjectAggregate) -> ProjectSnapshot:
    """Convert every current aggregate field explicitly without persistence access."""
    return ProjectSnapshot(
        project_id=str(aggregate.project.id),
        current_revision_id=str(aggregate.current_revision.id),
        revision_number=int(aggregate.current_revision.revision_number),
        concurrency_version=int(aggregate.project.concurrency_version),
        title=str(aggregate.current_revision.title),
        description=str(aggregate.current_revision.description),
        created_at=aggregate.project.created_at,
        updated_at=aggregate.project.updated_at,
        revision_created_at=aggregate.current_revision.created_at,
        head_updated_at=aggregate.head.updated_at,
    )


__all__ = ["project_snapshot_from_aggregate"]
