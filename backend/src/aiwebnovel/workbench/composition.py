"""Own the workbench storage adapter; importing this factory never registers ORM models."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.workbench.service import WorkbenchService


def compose_workbench(
    sessions: Callable[[], Session], projects: ProjectQueryService
) -> WorkbenchService:
    from aiwebnovel.workbench.persistence import SqlAlchemyWorkbenchRepository

    return WorkbenchService(SqlAlchemyWorkbenchRepository(sessions, projects))
