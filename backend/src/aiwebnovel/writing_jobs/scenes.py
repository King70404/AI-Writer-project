"""Author-recorded scene progress for writing plan chapters; never calls a model.

Every mark names the chapter plan revision it was made against. When the author saves
a new plan, earlier marks are shown against their own revision and flagged for
re-checking instead of being remapped onto the new scene list.
"""

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from aiwebnovel.chapter_planning.persistence import ChapterPlanRevisionRecord
    from aiwebnovel.writing_jobs.persistence import WritingJobRecord

SETTLED = ("done", "skipped")


def current_plan(session: Session, chapter_id: str) -> "ChapterPlanRevisionRecord | None":
    from aiwebnovel.chapter_planning.persistence import ChapterPlanRevisionRecord
    from aiwebnovel.novel_structure.identifiers import ChapterId

    return session.scalar(
        select(ChapterPlanRevisionRecord)
        .where(ChapterPlanRevisionRecord.chapter_id == ChapterId.parse(chapter_id))
        .order_by(ChapterPlanRevisionRecord.version.desc())
        .limit(1)
    )


def step_adopted(session: Session, job_id: str, step_index: int) -> bool:
    from aiwebnovel.ai_writing.persistence.models import AIWorkflowCandidateRecord
    from aiwebnovel.writing_jobs.persistence import WritingJobRunRecord

    return (
        session.scalar(
            select(AIWorkflowCandidateRecord.id)
            .join(
                WritingJobRunRecord,
                WritingJobRunRecord.run_id == AIWorkflowCandidateRecord.run_id,
            )
            .where(
                WritingJobRunRecord.job_id == job_id,
                WritingJobRunRecord.step_index == step_index,
                AIWorkflowCandidateRecord.status == "adopted",
            )
            .limit(1)
        )
        is not None
    )


def step_progress(session: Session, job: "WritingJobRecord", step_index: int) -> dict[str, object]:
    from aiwebnovel.chapter_planning.persistence import ChapterPlanRevisionRecord
    from aiwebnovel.writing_jobs.persistence import WritingJobSceneMarkRecord

    chapter_id = job.chapter_ids[step_index]
    marks = session.scalars(
        select(WritingJobSceneMarkRecord)
        .where(
            WritingJobSceneMarkRecord.job_id == job.id,
            WritingJobSceneMarkRecord.step_index == step_index,
        )
        .order_by(WritingJobSceneMarkRecord.sequence)
    ).all()
    current = current_plan(session, chapter_id)
    basis_id = marks[-1].plan_revision_id if marks else (current.id if current else None)
    basis = (
        current
        if current is not None and current.id == basis_id
        else (session.get(ChapterPlanRevisionRecord, basis_id) if basis_id else None)
    )
    if basis is not None and str(basis.chapter_id) != chapter_id:
        basis = None
    scenes = [
        (str(scene.get("id", "")), str(scene.get("title", "")))
        for scene in (basis.payload.get("scenes", []) if basis is not None else [])
        if isinstance(scene, dict)
    ]
    status = {scene_id: "pending" for scene_id, _ in scenes}
    target: str | None = None
    for mark in marks:
        if mark.plan_revision_id != basis_id:
            continue
        if mark.action == "recheck":
            status = {scene_id: "pending" for scene_id, _ in scenes}
            target = None
        elif mark.scene_id in status:
            if mark.action == "target":
                target = mark.scene_id
            else:
                status[mark.scene_id] = mark.action
    if target is not None and status.get(target) in SETTLED:
        target = None
    pending = [scene_id for scene_id, _ in scenes if status[scene_id] == "pending"]
    return {
        "step_index": step_index,
        "chapter_id": chapter_id,
        "plan_revision_id": basis.id if basis is not None else None,
        "plan_version": basis.version if basis is not None else None,
        "current_plan_revision_id": current.id if current is not None else None,
        "current_plan_version": current.version if current is not None else None,
        "needs_recheck": bool(marks) and (current is None or current.id != basis_id),
        "has_adopted": step_adopted(session, job.id, step_index),
        "scenes": [
            {"scene_id": scene_id, "title": title, "status": status[scene_id]}
            for scene_id, title in scenes
        ],
        "target_scene_id": target,
        "next_scene_id": target or (pending[0] if pending else None),
        "done_count": sum(value == "done" for value in status.values()),
        "skipped_count": sum(value == "skipped" for value in status.values()),
        "total": len(scenes),
    }
