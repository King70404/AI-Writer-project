"""Manual chapter plans; no model requests are made by these endpoints."""

from collections.abc import Generator
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.web import require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.imports.web import import_session
from aiwebnovel.writing_jobs.scenes import SETTLED, step_adopted, step_progress

if TYPE_CHECKING:
    from aiwebnovel.writing_jobs.persistence import WritingJobRecord


class CreateJob(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=120)
    chapter_ids: list[str] = Field(min_length=1, max_length=10)
    max_requests: int = Field(default=10, ge=1, le=10)
    max_output_characters: int = Field(default=3000, ge=200, le=3000)


class BindRun(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    run_id: str = Field(min_length=36, max_length=36)


class MarkScene(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    step_index: int = Field(ge=0, le=9)
    plan_revision_id: str = Field(min_length=1, max_length=36)
    action: Literal["target", "done", "skipped", "pending", "recheck"]
    scene_id: str | None = Field(
        default=None, min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$"
    )


class ChangeJob(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)


def fail(code: str, status: int = 409) -> AppError:
    return AppError(code=code, message="Writing plan cannot be changed.", status_code=status)


def session_dep(request: Request, response: Response) -> Generator[Session, None, None]:
    parent = import_session(request, response)
    try:
        session = next(parent)
        inspector = inspect(session.get_bind())
        if not all(
            inspector.has_table(name)
            for name in (
                "writing_jobs",
                "writing_job_budgets",
                "writing_job_runs",
                "writing_job_scene_marks",
            )
        ):
            raise fail("WRITING_JOB_UNAVAILABLE", 503)
        session.info["writing_job_project_store"] = request.app.state.writing_job_project_store
        yield session
    finally:
        parent.close()


def render(row: object, session: Session) -> dict[str, object]:
    from aiwebnovel.writing_jobs.persistence import (
        WritingJobBudgetRecord,
        WritingJobRecord,
        WritingJobRunRecord,
    )

    assert isinstance(row, WritingJobRecord)
    from aiwebnovel.ai_writing.persistence.models import (
        AICandidateEditAdoptionRecord,
        AICandidateEditRecord,
        AIWorkflowCandidateRecord,
        AIWorkflowRunRecord,
    )

    budget = session.get(WritingJobBudgetRecord, row.id)
    active = session.scalar(
        select(WritingJobRunRecord).where(
            WritingJobRunRecord.job_id == row.id,
            WritingJobRunRecord.step_index == row.current_index,
        )
    )
    bindings = session.scalars(
        select(WritingJobRunRecord).where(WritingJobRunRecord.job_id == row.id)
    ).all()
    runs = [session.get(AIWorkflowRunRecord, binding.run_id) for binding in bindings]
    generated_characters = sum(
        int(run.payload.get("generated_characters", 0)) for run in runs if run is not None
    )
    adopted_characters = 0
    for run in runs:
        if run is None:
            continue
        for candidate in session.scalars(
            select(AIWorkflowCandidateRecord).where(
                AIWorkflowCandidateRecord.run_id == run.id,
                AIWorkflowCandidateRecord.status == "adopted",
            )
        ):
            adoption = session.get(AICandidateEditAdoptionRecord, candidate.id)
            edit = session.get(AICandidateEditRecord, adoption.edit_id) if adoption else None
            adopted_text = edit.text if edit else candidate.text
            adopted_characters += sum(not character.isspace() for character in adopted_text)
    # A chapter draft bound as a step counts its own generated and adopted segments.
    from aiwebnovel.ai_writing.persistence.chapter_drafts import ChapterDraftRecord

    active_draft_id = None
    drafts: list[dict[str, object]] = []
    has_drafts = inspect(session.get_bind()).has_table("chapter_drafts")
    for binding in sorted(bindings, key=lambda item: item.step_index) if has_drafts else ():
        draft = session.get(ChapterDraftRecord, binding.run_id)
        if draft is None:
            continue
        if active is not None and binding.run_id == active.run_id:
            active_draft_id = draft.id
        segments = draft.payload.get("segments", [])
        # An author's edit is what was adopted, so it is what the job counts.
        draft_adopted = sum(
            int(
                segment["characters"]
                if segment.get("edited_characters") is None
                else segment["edited_characters"]
            )
            for segment in segments
            if segment.get("status") == "adopted"
        )
        draft_generated = int(draft.payload.get("generated_characters", 0))
        generated_characters += draft_generated
        adopted_characters += draft_adopted
        # Counts only: the drawer links to the chapter; no segment text leaves this summary.
        drafts.append(
            {
                "draft_id": draft.id,
                "chapter_id": str(draft.chapter_id),
                "step_index": binding.step_index,
                "status": draft.payload.get("status"),
                "segments": len(segments),
                "pending": sum(item.get("status") == "pending" for item in segments),
                "adopted": sum(item.get("status") == "adopted" for item in segments),
                "discarded": sum(item.get("status") == "discarded" for item in segments),
                "edited": sum(item.get("edited_text") is not None for item in segments),
                "generated_characters": draft_generated,
                "adopted_characters": draft_adopted,
                "created_at": draft.created_at,
            }
        )
    return {
        "generated_characters": generated_characters,
        "adopted_characters": adopted_characters,
        "max_requests": budget.max_requests if budget else 0,
        "max_output_characters": budget.max_output_characters if budget else 0,
        "claimed_requests": budget.claimed_requests if budget else 0,
        "used_characters": budget.used_characters if budget else 0,
        "active_run_id": active.run_id if active else None,
        "active_draft_id": active_draft_id,
        "drafts": drafts,
        "job_id": row.id,
        "project_id": row.project_id,
        "title": row.title,
        "status": row.status,
        "version": row.version,
        "current_index": row.current_index,
        "steps": [
            {
                "chapter_id": chapter,
                "status": "completed" if index < row.current_index else "pending",
            }
            for index, chapter in enumerate(row.chapter_ids)
        ],
        "scene_progress": [
            step_progress(session, row, index) for index in range(len(row.chapter_ids))
        ],
    }


def router(api_prefix: str) -> APIRouter:
    r = APIRouter(prefix=api_prefix, tags=["Writing jobs"])
    SessionDep = Annotated[Session, Depends(session_dep)]
    Json = Annotated[None, Depends(require_json)]

    def get(session: Session, job_id: str) -> "WritingJobRecord":
        from aiwebnovel.writing_jobs.persistence import WritingJobRecord

        row = session.scalar(
            select(WritingJobRecord).where(
                WritingJobRecord.id == job_id,
                WritingJobRecord.project_id.in_(
                    session.info["writing_job_project_store"].active_project_ids()
                ),
            )
        )
        if row is None:
            raise fail("WRITING_JOB_NOT_FOUND", 404)
        return row

    @r.post("/projects/{project_id}/writing-jobs", status_code=201)
    def create(project_id: str, body: CreateJob, session: SessionDep, _: Json) -> dict[str, object]:
        from aiwebnovel.domain.errors import DomainError
        from aiwebnovel.novel_structure.persistence.workflow_transaction import (
            load_workflow_chapter,
        )
        from aiwebnovel.writing_jobs.persistence import WritingJobBudgetRecord, WritingJobRecord

        if not body.title.strip() or len(set(body.chapter_ids)) != len(body.chapter_ids):
            raise fail("WRITING_JOB_INVALID", 422)
        session.execute(text("BEGIN IMMEDIATE"))
        try:
            chapters = [load_workflow_chapter(session, chapter) for chapter in body.chapter_ids]
        except DomainError:
            raise fail("WRITING_JOB_INVALID", 422) from None
        if any(str(chapter.chapter.project_id) != project_id for chapter in chapters):
            raise fail("WRITING_JOB_INVALID", 422)
        if (
            len(
                session.scalars(
                    select(WritingJobRecord.id)
                    .where(WritingJobRecord.project_id == project_id)
                    .limit(100)
                ).all()
            )
            >= 100
        ):
            raise fail("WRITING_JOB_LIMIT", 422)
        row = WritingJobRecord(
            id=str(uuid4()),
            project_id=project_id,
            title=body.title.strip(),
            status="planned",
            version=1,
            current_index=0,
            chapter_ids=body.chapter_ids,
        )
        session.add(row)
        session.add(
            WritingJobBudgetRecord(
                job_id=row.id,
                max_requests=body.max_requests,
                max_output_characters=body.max_output_characters,
                claimed_requests=0,
                used_characters=0,
            )
        )
        session.commit()
        return render(row, session)

    @r.get("/projects/{project_id}/writing-jobs")
    def listing(project_id: str, session: SessionDep) -> list[dict[str, object]]:
        from aiwebnovel.writing_jobs.persistence import WritingJobRecord

        rows = session.scalars(
            select(WritingJobRecord)
            .where(
                WritingJobRecord.project_id == project_id,
                WritingJobRecord.project_id.in_(
                    session.info["writing_job_project_store"].active_project_ids()
                ),
            )
            .order_by(WritingJobRecord.id)
            .limit(100)
        ).all()
        return [render(row, session) for row in rows]

    @r.get("/writing-jobs/{job_id}")
    def read(job_id: str, session: SessionDep) -> dict[str, object]:
        return render(get(session, job_id), session)

    @r.post("/writing-jobs/{job_id}/bind-run")
    def bind(job_id: str, body: BindRun, session: SessionDep, _: Json) -> dict[str, object]:
        from aiwebnovel.ai_writing.persistence.models import (
            AIWorkflowCandidateRecord,
            AIWorkflowRunRecord,
        )
        from aiwebnovel.writing_jobs.persistence import WritingJobRunRecord

        session.execute(text("BEGIN IMMEDIATE"))
        job = get(session, job_id)
        run = session.get(AIWorkflowRunRecord, body.run_id)
        if (
            job.version != body.expected_version
            or job.status != "planned"
            or run is None
            or job.current_index >= len(job.chapter_ids)
            or str(run.chapter_id) != job.chapter_ids[job.current_index]
            or run.status != "ready"
            or run.payload.get("generated_steps") != 0
            or run.payload.get("in_flight")
            or session.get(WritingJobRunRecord, body.run_id) is not None
            or session.scalar(
                select(AIWorkflowCandidateRecord.id)
                .where(AIWorkflowCandidateRecord.run_id == body.run_id)
                .limit(1)
            )
            is not None
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
            raise fail("WRITING_JOB_CONFLICT")
        session.add(
            WritingJobRunRecord(
                run_id=run.id, job_id=job.id, step_index=job.current_index, reserved_characters=0
            )
        )
        job.version += 1
        session.commit()
        return render(job, session)

    @r.post("/writing-jobs/{job_id}/scene-progress")
    def mark_scene(job_id: str, body: MarkScene, session: SessionDep, _: Json) -> dict[str, object]:
        """Record one author decision about a planned scene; no model request is made."""
        from datetime import UTC, datetime

        from aiwebnovel.writing_jobs.persistence import WritingJobSceneMarkRecord

        session.execute(text("BEGIN IMMEDIATE"))
        job = get(session, job_id)
        if (
            job.version != body.expected_version
            or job.status not in ("planned", "paused")
            or body.step_index != job.current_index
            or body.step_index >= len(job.chapter_ids)
        ):
            raise fail("WRITING_JOB_CONFLICT")
        progress = step_progress(session, job, body.step_index)
        if body.plan_revision_id != progress["current_plan_revision_id"]:
            raise fail("WRITING_JOB_SCENE_PLAN_CHANGED")
        if body.action == "recheck":
            if body.scene_id is not None or not progress["needs_recheck"]:
                raise fail("WRITING_JOB_CONFLICT")
        else:
            if progress["needs_recheck"]:
                raise fail("WRITING_JOB_SCENE_RECHECK_REQUIRED")
            scenes = progress["scenes"]
            assert isinstance(scenes, list)
            status = {scene["scene_id"]: scene["status"] for scene in scenes}
            if body.scene_id is None or body.scene_id not in status:
                raise fail("WRITING_JOB_INVALID", 422)
            current = status[body.scene_id]
            if body.action == "pending":
                allowed = current in SETTLED
            elif body.action == "target":
                allowed = current == "pending" and progress["target_scene_id"] != body.scene_id
            else:
                allowed = current == "pending"
            # Only an author adoption already recorded for this chapter step can back a
            # "done" mark; nothing here inspects or judges the generated text.
            if body.action == "done" and allowed:
                allowed = step_adopted(session, job.id, body.step_index)
            if not allowed:
                raise fail("WRITING_JOB_CONFLICT")
        session.add(
            WritingJobSceneMarkRecord(
                id=str(uuid4()),
                job_id=job.id,
                step_index=body.step_index,
                sequence=job.version,
                plan_revision_id=body.plan_revision_id,
                scene_id=body.scene_id,
                action=body.action,
                created_at=datetime.now(UTC),
            )
        )
        job.version += 1
        session.commit()
        return render(job, session)

    @r.post("/writing-jobs/{job_id}/{action}")
    def change(
        job_id: str,
        action: Literal["pause", "resume", "cancel", "finish-step"],
        body: ChangeJob,
        session: SessionDep,
        _: Json,
    ) -> dict[str, object]:
        session.execute(text("BEGIN IMMEDIATE"))
        row = get(session, job_id)
        if row.version != body.expected_version:
            raise fail("WRITING_JOB_CONFLICT")
        if action == "pause" and row.status == "planned":
            row.status = "paused"
        elif action == "resume" and row.status == "paused":
            row.status = "planned"
        elif action == "cancel" and row.status in ("planned", "paused"):
            row.status = "cancelled"
        elif action == "finish-step" and row.status == "planned":
            from aiwebnovel.ai_writing.persistence.models import (
                AIWorkflowCandidateRecord,
                AIWorkflowRunRecord,
            )
            from aiwebnovel.writing_jobs.persistence import WritingJobRunRecord

            bindings = session.scalars(
                select(WritingJobRunRecord).where(
                    WritingJobRunRecord.job_id == row.id,
                    WritingJobRunRecord.step_index == row.current_index,
                )
            ).all()
            for binding in bindings:
                run = session.get(AIWorkflowRunRecord, binding.run_id)
                pending = session.scalar(
                    select(AIWorkflowCandidateRecord.id)
                    .where(
                        AIWorkflowCandidateRecord.run_id == binding.run_id,
                        AIWorkflowCandidateRecord.status == "pending",
                    )
                    .limit(1)
                )
                if (run is not None and run.payload.get("in_flight")) or pending is not None:
                    raise fail("WRITING_JOB_CONFLICT")
            row.current_index += 1
            if row.current_index == len(row.chapter_ids):
                row.status = "completed"
        else:
            raise fail("WRITING_JOB_CONFLICT")
        row.version += 1
        session.commit()
        return render(row, session)

    return r
