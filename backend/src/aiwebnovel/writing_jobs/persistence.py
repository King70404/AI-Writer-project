"""Writing plans persisted independently of model tasks."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aiwebnovel.db.base import Base


class WritingJobRecord(Base):
    __tablename__ = "writing_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class WritingJobBudgetRecord(Base):
    __tablename__ = "writing_job_budgets"
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    max_requests: Mapped[int] = mapped_column(Integer, nullable=False)
    max_output_characters: Mapped[int] = mapped_column(Integer, nullable=False)
    claimed_requests: Mapped[int] = mapped_column(Integer, nullable=False)
    used_characters: Mapped[int] = mapped_column(Integer, nullable=False)


class WritingJobRunRecord(Base):
    __tablename__ = "writing_job_runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_characters: Mapped[int] = mapped_column(Integer, nullable=False)


class WritingJobSceneMarkRecord(Base):
    """Append-only author marks; each one names the plan revision it was made against."""

    __tablename__ = "writing_job_scene_marks"
    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="uq_writing_job_scene_mark_sequence"),
        CheckConstraint(
            "action IN ('target','done','skipped','pending','recheck')",
            name="ck_writing_job_scene_mark_action",
        ),
        Index("ix_writing_job_scene_marks_job", "job_id", "step_index"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    scene_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
