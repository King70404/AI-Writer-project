"""Own the usage ledger storage adapter; importing this factory never registers ORM models."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.usage.service import UsageLedgerService


def compose_usage_ledger(
    sessions: Callable[[], Session], projects: ProjectQueryService
) -> UsageLedgerService:
    from aiwebnovel.usage.persistence import SqlAlchemyUsageLedger

    return UsageLedgerService(SqlAlchemyUsageLedger(sessions, projects))
