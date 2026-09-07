"""Deterministic SQLAlchemy statements for the Project repository adapter."""

from datetime import datetime

from sqlalchemy import Select, Update, select, update

from aiwebnovel.project import ConcurrencyVersion
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.models import (
    ProjectHeadRecord,
    ProjectRecord,
    ProjectRevisionRecord,
)


def current_project_query(
    project_id: ProjectId,
) -> Select[tuple[ProjectRecord, ProjectHeadRecord, ProjectRevisionRecord]]:
    """Select one active Project and its current pointer target without loading history."""
    return (
        select(ProjectRecord, ProjectHeadRecord, ProjectRevisionRecord)
        .outerjoin(
            ProjectHeadRecord,
            ProjectHeadRecord.project_id == ProjectRecord.id,
        )
        .outerjoin(
            ProjectRevisionRecord,
            ProjectRevisionRecord.id == ProjectHeadRecord.revision_id,
        )
        .where(
            ProjectRecord.id == project_id,
            ProjectRecord.deleted_at.is_(None),
        )
    )


def project_compare_and_swap(
    project_id: ProjectId,
    expected_version: ConcurrencyVersion,
    new_version: ConcurrencyVersion,
    updated_at: datetime,
) -> Update:
    """Update an active stable Project only when its persisted version still matches."""
    return (
        update(ProjectRecord)
        .where(
            ProjectRecord.id == project_id,
            ProjectRecord.concurrency_version == expected_version,
            ProjectRecord.deleted_at.is_(None),
        )
        .values(concurrency_version=new_version, updated_at=updated_at)
    )


def project_logical_delete(
    project_id: ProjectId,
    expected_version: ConcurrencyVersion,
    deleted_at: datetime,
) -> Update:
    """Hide one active Project without deleting its immutable revision history."""
    return (
        update(ProjectRecord)
        .where(
            ProjectRecord.id == project_id,
            ProjectRecord.concurrency_version == expected_version,
            ProjectRecord.deleted_at.is_(None),
        )
        .values(
            concurrency_version=ConcurrencyVersion(int(expected_version) + 1),
            updated_at=deleted_at,
            deleted_at=deleted_at,
        )
    )


def head_compare_and_swap(
    project_id: ProjectId,
    expected_revision_id: ProjectRevisionId,
    new_revision_id: ProjectRevisionId,
    updated_at: datetime,
) -> Update:
    """Move a Project head only when it still targets the expected revision."""
    return (
        update(ProjectHeadRecord)
        .where(
            ProjectHeadRecord.project_id == project_id,
            ProjectHeadRecord.revision_id == expected_revision_id,
        )
        .values(revision_id=new_revision_id, updated_at=updated_at)
    )


__all__ = [
    "current_project_query",
    "head_compare_and_swap",
    "project_compare_and_swap",
    "project_logical_delete",
]
