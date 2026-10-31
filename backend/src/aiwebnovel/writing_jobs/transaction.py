"""Job budget checks inside the existing workflow write transaction."""

from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.application.workflow_models import WorkflowConflict

if TYPE_CHECKING:
    from aiwebnovel.writing_jobs.persistence import (
        WritingJobBudgetRecord,
        WritingJobRecord,
        WritingJobRunRecord,
    )


def bound(
    session: Session, run_id: str
) -> tuple["WritingJobRunRecord", "WritingJobRecord", "WritingJobBudgetRecord"] | None:
    from aiwebnovel.writing_jobs.persistence import (
        WritingJobBudgetRecord,
        WritingJobRecord,
        WritingJobRunRecord,
    )

    if not inspect(session.get_bind()).has_table("writing_job_runs"):
        return None
    binding = session.get(WritingJobRunRecord, run_id)
    if binding is None:
        return None
    job = session.get(WritingJobRecord, binding.job_id)
    budget = session.get(WritingJobBudgetRecord, binding.job_id)
    if job is None or budget is None:
        raise WorkflowConflict
    return binding, job, budget


def claim(session: Session, run_id: str, upper: int) -> None:
    value = bound(session, run_id)
    if value is None:
        return
    binding, job, budget = value
    if (
        job.status != "planned"
        or binding.step_index != job.current_index
        or budget.claimed_requests >= budget.max_requests
        or budget.used_characters + upper > budget.max_output_characters
        or binding.reserved_characters
    ):
        raise WorkflowConflict
    budget.claimed_requests += 1
    budget.used_characters += upper
    binding.reserved_characters = upper


def settle(session: Session, run_id: str, actual: int | None, *, unsent: bool = False) -> None:
    value = bound(session, run_id)
    if value is None:
        return
    binding, _, budget = value
    if not binding.reserved_characters:
        return
    if unsent:
        budget.claimed_requests -= 1
        budget.used_characters -= binding.reserved_characters
    elif actual is not None:
        budget.used_characters += actual - binding.reserved_characters
    # A failed or interrupted request may have been billed: retain its reservation.
    binding.reserved_characters = 0
