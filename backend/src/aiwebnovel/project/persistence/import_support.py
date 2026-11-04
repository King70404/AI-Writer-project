"""Project-owned persistence operations for atomic manuscript imports."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.mappers import project_aggregate_to_records
from aiwebnovel.project.persistence.models import ProjectHeadRecord, ProjectRevisionRecord


class ImportProjectStore:
    def persist(self, session: Session, project: ProjectAggregate) -> None:
        stable, head, revision = project_aggregate_to_records(project)
        for row in (stable, revision, head):
            session.add(row)
            session.flush()

    def current_title(self, session: Session, project_id: str) -> str | None:
        result: str | None = session.execute(
            select(ProjectRevisionRecord.title)
            .join(ProjectHeadRecord, ProjectHeadRecord.revision_id == ProjectRevisionRecord.id)
            .where(ProjectHeadRecord.project_id == ProjectId.parse(project_id))
        ).scalar_one_or_none()
        return result
