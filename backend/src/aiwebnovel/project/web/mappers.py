"""Explicit mapping from Project application snapshots to HTTP DTOs."""

from aiwebnovel.project.application.models import ProjectSnapshot
from aiwebnovel.project.web.dto import ProjectResponse


def project_response_from_snapshot(snapshot: ProjectSnapshot) -> ProjectResponse:
    """Copy each public snapshot field into an immutable response DTO."""
    if type(snapshot) is not ProjectSnapshot:
        raise TypeError("snapshot must be a ProjectSnapshot")
    return ProjectResponse(
        project_id=snapshot.project_id,
        current_revision_id=snapshot.current_revision_id,
        revision_number=snapshot.revision_number,
        concurrency_version=snapshot.concurrency_version,
        title=snapshot.title,
        description=snapshot.description,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        revision_created_at=snapshot.revision_created_at,
        head_updated_at=snapshot.head_updated_at,
    )


__all__ = ["project_response_from_snapshot"]
