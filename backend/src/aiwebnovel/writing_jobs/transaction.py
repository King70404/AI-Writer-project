"""Job budget checks inside the existing workflow write transaction."""

from typing import TYPE_CHECKING

from sqlalchemy import inspect, select
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


def bind_current_step(
    session: Session, run_id: str, job_id: str, project_id: str, chapter_id: str
) -> bool:
    """Bind a new run (or chapter draft) as the job's current, still unbound step.

    Returns False, writing nothing, unless the job belongs to the project, is planned, its
    current step is this chapter and no run is bound to that step yet.
    """
    from aiwebnovel.writing_jobs.persistence import WritingJobRecord, WritingJobRunRecord

    job = session.get(WritingJobRecord, job_id)
    if (
        job is None
        or job.project_id != project_id
        or job.status != "planned"
        or job.current_index >= len(job.chapter_ids)
        or job.chapter_ids[job.current_index] != chapter_id
        or session.scalar(
            select(WritingJobRunRecord.run_id)
            .where(
                WritingJobRunRecord.job_id == job.id,
                WritingJobRunRecord.step_index == job.current_index,
            )
            .limit(1)
        )
        is not None
    ):
        return False
    session.add(
        WritingJobRunRecord(
            run_id=run_id, job_id=job.id, step_index=job.current_index, reserved_characters=0
        )
    )
    job.version += 1
    return True
