"""Explicit mapping from Project application snapshots to HTTP DTOs."""

from aiwebnovel.project.application.models import (
    ProjectListPage,
    ProjectRevisionHistoryPage,
    ProjectRevisionHistorySnapshot,
    ProjectSnapshot,
)
from aiwebnovel.project.web.cursors import encode_project_list_cursor
from aiwebnovel.project.web.dto import (
    ProjectListItemResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectRevisionHistoryItemResponse,
    ProjectRevisionHistoryResponse,
    ProjectRevisionResponse,
)
from aiwebnovel.project.web.revision_cursors import encode_project_revision_cursor


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


def project_revision_history_response_from_page(
    page: ProjectRevisionHistoryPage,
) -> ProjectRevisionHistoryResponse:
    """Map one application history page and encode only its next position."""
    if type(page) is not ProjectRevisionHistoryPage:
        raise TypeError("page must be a ProjectRevisionHistoryPage")
    return ProjectRevisionHistoryResponse(
        project_id=page.project_id,
        current_revision_number=page.current_revision_number,
        items=tuple(
            ProjectRevisionHistoryItemResponse(
                revision_id=item.revision_id,
                revision_number=item.revision_number,
                title=item.title,
                created_at=item.created_at,
                is_current=item.is_current,
            )
            for item in page.items
        ),
        next_cursor=(
            encode_project_revision_cursor(page.next_position)
            if page.next_position is not None
            else None
        ),
        has_more=page.has_more,
    )


def project_revision_response_from_snapshot(
    snapshot: ProjectRevisionHistorySnapshot,
) -> ProjectRevisionResponse:
    """Copy each immutable revision field into the HTTP response DTO."""
    if type(snapshot) is not ProjectRevisionHistorySnapshot:
        raise TypeError("snapshot must be a ProjectRevisionHistorySnapshot")
    return ProjectRevisionResponse(
        project_id=snapshot.project_id,
        revision_id=snapshot.revision_id,
        revision_number=snapshot.revision_number,
        title=snapshot.title,
        description=snapshot.description,
        created_at=snapshot.created_at,
        is_current=snapshot.is_current,
        current_revision_number=snapshot.current_revision_number,
    )


__all__ = [
    "project_list_response_from_page",
    "project_response_from_snapshot",
    "project_revision_history_response_from_page",
    "project_revision_response_from_snapshot",
]
