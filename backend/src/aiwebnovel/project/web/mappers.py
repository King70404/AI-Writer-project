"""Explicit mapping from Project application snapshots to HTTP DTOs."""

from aiwebnovel.project.application.models import ProjectListPage, ProjectSnapshot
from aiwebnovel.project.web.cursors import encode_project_list_cursor
from aiwebnovel.project.web.dto import (
    ProjectListItemResponse,
    ProjectListResponse,
    ProjectResponse,
)


def project_list_response_from_page(page: ProjectListPage) -> ProjectListResponse:
    """Explicitly map an application page and encode only its next position."""
    if type(page) is not ProjectListPage:
        raise TypeError("page must be a ProjectListPage")
    items = tuple(
        ProjectListItemResponse(
            project_id=item.project_id,
            current_revision_id=item.current_revision_id,
            revision_number=item.revision_number,
            concurrency_version=item.concurrency_version,
            title=item.title,
            created_at=item.created_at,
            updated_at=item.updated_at,
            revision_created_at=item.revision_created_at,
        )
        for item in page.items
    )
    return ProjectListResponse(
        items=items,
        next_cursor=(
            encode_project_list_cursor(page.next_position)
            if page.next_position is not None
            else None
        ),
        has_more=page.has_more,
    )


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


__all__ = ["project_list_response_from_page", "project_response_from_snapshot"]
