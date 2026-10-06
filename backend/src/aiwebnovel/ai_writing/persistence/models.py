"""AI drafts and adoption receipts, separate from immutable author revisions."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.novel_structure.identifiers import ChapterId
from aiwebnovel.project.identifiers import ProjectId


class AIWorkflowRunRecord(Base):
    __tablename__ = "ai_workflow_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ready','generating','paused','interrupted','completed')",
            name="ck_ai_runs_status",
        ),
        Index("ix_ai_runs_chapter", "chapter_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    chapter_id: Mapped[ChapterId] = mapped_column(
        PrefixedUlidType(ChapterId), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class AIWorkflowCandidateRecord(Base):
    __tablename__ = "ai_workflow_candidates"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_ai_candidates_run_sequence"),
        UniqueConstraint("chapter_id", "idempotency_key", name="uq_ai_candidates_adoption_key"),
        CheckConstraint("sequence > 0", name="ck_ai_candidates_sequence"),
        CheckConstraint("character_count BETWEEN 200 AND 300", name="ck_ai_candidates_size"),
        CheckConstraint(
            "status IN ('pending','adopted','discarded')", name="ck_ai_candidates_status"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_workflow_runs.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_id: Mapped[ChapterId] = mapped_column(
        PrefixedUlidType(ChapterId), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    character_count: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    adopted_revision_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    adopted_version: Mapped[int | None] = mapped_column(nullable=True)
