"""Project-owned query for author writing plans."""

from sqlalchemy.sql import Select

from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import ProjectRecord


class WritingJobProjectStore:
    def active_project_ids(self) -> Select[tuple[ProjectId]]:
        return ProjectRecord.active_ids()
