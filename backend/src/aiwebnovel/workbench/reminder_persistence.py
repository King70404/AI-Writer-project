"""Batch metadata projections of existing story and usage records; no manuscript reads."""

import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_control.persistence import StoryControlRevisionRecord as ThreadRecord
from aiwebnovel.usage.budget import AttemptCost, summarize
from aiwebnovel.usage.budget_persistence import (
    ModelBudgetReservationRecord as Reservation,
)
from aiwebnovel.usage.budget_persistence import (
    ModelPriceRevisionRecord as Price,
)
from aiwebnovel.usage.budget_persistence import (
    ProjectBudgetRevisionRecord as BudgetRecord,
)
from aiwebnovel.usage.budget_persistence import (
    month_start,
)
from aiwebnovel.usage.persistence import ModelUsageAttemptRecord as Attempt
from aiwebnovel.workbench.snapshot import BudgetReminderRow, ThreadReminderRow


def load_reminders(
    session: Session, projects: tuple[ProjectId, ...]
) -> tuple[dict[str, tuple[ThreadReminderRow, ...]], dict[str, BudgetReminderRow]]:
    latest_threads = (
        select(ThreadRecord.entity_id, func.max(ThreadRecord.version).label("version"))
        .where(ThreadRecord.project_id.in_(projects), ThreadRecord.kind == "thread")
        .group_by(ThreadRecord.entity_id)
        .subquery()
    )
    threads: dict[str, list[ThreadReminderRow]] = defaultdict(list)
    rows = session.execute(
        select(
            ThreadRecord.project_id,
            ThreadRecord.entity_id,
            *[
                func.json_extract(ThreadRecord.payload, f"$.{name}")
                for name in (
                    "title",
                    "status",
                    "planned_payoff_chapter_id",
                    "planned_payoff_volume_id",
                    "anchors",
                )
            ],
        )
        .join(
            latest_threads,
            and_(
                ThreadRecord.entity_id == latest_threads.c.entity_id,
                ThreadRecord.version == latest_threads.c.version,
            ),
        )
        .where(ThreadRecord.kind == "thread")
    )
    for row in rows:
        anchors = json.loads(row[6]) if isinstance(row[6], str) else []
        threads[str(row[0])].append(
            ThreadReminderRow(
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                tuple((anchor["chapter_id"], anchor["chapter_revision_id"]) for anchor in anchors),
            )
        )
    latest_budgets = (
        select(BudgetRecord.project_id, func.max(BudgetRecord.version).label("version"))
        .where(BudgetRecord.project_id.in_(projects))
        .group_by(BudgetRecord.project_id)
        .subquery()
    )
    budgets = list(
        session.scalars(
            select(BudgetRecord).join(
                latest_budgets,
                and_(
                    BudgetRecord.project_id == latest_budgets.c.project_id,
                    BudgetRecord.version == latest_budgets.c.version,
                ),
            )
        )
    )
    active = tuple(budget.project_id for budget in budgets if budget.mode != "off")
    costs: dict[str, list[AttemptCost]] = defaultdict(list)
    if active:
        attempts = session.execute(
            select(
                Attempt.project_id,
                Attempt.status,
                Attempt.reported_input_tokens,
                Attempt.reported_output_tokens,
                Attempt.reported_total_tokens,
                Reservation.reserved_micros,
                Reservation.currency,
                Price.input_micros_per_million,
                Price.output_micros_per_million,
            )
            .outerjoin(Reservation, Reservation.attempt_id == Attempt.id)
            .outerjoin(Price, Price.id == Reservation.price_revision_id)
            .where(
                Attempt.project_id.in_(active),
                Attempt.started_at >= month_start(datetime.now(UTC), None),
            )
        )
        for row in attempts:
            costs[str(row[0])].append(AttemptCost(*row[1:]))
    return (
        {key: tuple(value) for key, value in threads.items()},
        {
            str(budget.project_id): BudgetReminderRow(
                budget.mode,
                budget.monthly_limit_micros,
                summarize(costs[str(budget.project_id)], budget.currency),
            )
            for budget in budgets
        },
    )
