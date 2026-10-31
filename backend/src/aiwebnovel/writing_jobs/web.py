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

if TYPE_CHECKING:
    from aiwebnovel.writing_jobs.persistence import WritingJobRecord


class CreateJob(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=120)
    chapter_ids: list[str] = Field(min_length=1, max_length=10)


class ChangeJob(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)


def fail(code: str, status: int = 409) -> AppError:
    return AppError(code=code, message="Writing plan cannot be changed.", status_code=status)


def session_dep(request: Request, response: Response) -> Generator[Session, None, None]:
    parent = import_session(request, response)
    try:
        session = next(parent)
        if not inspect(session.get_bind()).has_table("writing_jobs"):
            raise fail("WRITING_JOB_UNAVAILABLE", 503)
        session.info["writing_job_project_store"] = request.app.state.writing_job_project_store
        yield session
    finally:
        parent.close()


def render(row: object) -> dict[str, object]:
    from aiwebnovel.writing_jobs.persistence import WritingJobRecord

    assert isinstance(row, WritingJobRecord)
    return {
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
        from aiwebnovel.writing_jobs.persistence import WritingJobRecord

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
        session.commit()
        return render(row)

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
        return [render(row) for row in rows]

    @r.get("/writing-jobs/{job_id}")
    def read(job_id: str, session: SessionDep) -> dict[str, object]:
        return render(get(session, job_id))

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
            row.current_index += 1
            if row.current_index == len(row.chapter_ids):
                row.status = "completed"
        else:
            raise fail("WRITING_JOB_CONFLICT")
        row.version += 1
        session.commit()
        return render(row)

    return r
