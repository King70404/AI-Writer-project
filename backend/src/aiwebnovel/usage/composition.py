"""Own the usage ledger and budget storage adapters; importing never registers ORM models."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from aiwebnovel.model_gateway.models import ModelProfile
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.usage.budget_service import UsageBudgetService
from aiwebnovel.usage.service import UsageLedgerService


def compose_usage_ledger(
    sessions: Callable[[], Session],
    projects: ProjectQueryService,
    profile_reader: Callable[[str], ModelProfile] | None = None,
) -> tuple[UsageLedgerService, UsageBudgetService | None]:
    """The ledger meters every request; with a profile reader it also enforces budgets."""
    from aiwebnovel.usage.budget_persistence import SqlAlchemyBudgetStore
    from aiwebnovel.usage.persistence import SqlAlchemyUsageLedger

    if profile_reader is None:
        return UsageLedgerService(SqlAlchemyUsageLedger(sessions, projects)), None
    store = SqlAlchemyBudgetStore(sessions, projects)
    return (
        UsageLedgerService(SqlAlchemyUsageLedger(sessions, projects, budgets=store)),
        UsageBudgetService(store, profile_reader),
    )
