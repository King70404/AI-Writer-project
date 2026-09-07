"""Shared persistence check for author-visible Projects."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from aiwebnovel.project.deletion import PROJECT_DELETION_TITLE_PREFIX
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import (
    ProjectHeadRecord,
    ProjectRecord,
    ProjectRevisionRecord,
)


def project_is_active(session: Session, project_id: ProjectId) -> bool:
    """Return True only when the Project exists and its current revision is not a tombstone."""
    if type(project_id) is not ProjectId:
        raise TypeError("project_id must be a ProjectId")
    statement = (
        select(ProjectRecord.id)
        .join(ProjectHeadRecord, ProjectHeadRecord.project_id == ProjectRecord.id)
        .join(
            ProjectRevisionRecord,
            ProjectRevisionRecord.id == ProjectHeadRecord.revision_id,
        )
        .where(
            ProjectRecord.id == project_id,
            ~ProjectRevisionRecord.title.startswith(PROJECT_DELETION_TITLE_PREFIX),
        )
    )
    return session.execute(statement).scalar_one_or_none() is not None


__all__ = ["project_is_active"]
