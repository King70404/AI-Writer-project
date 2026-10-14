"""Append-only plans with project visibility and optimistic concurrency in one transaction."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from aiwebnovel.chapter_planning.models import ChapterPlan, PlanningConflict, SaveChapterPlan
from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.novel_structure.identifiers import ChapterId
from aiwebnovel.novel_structure.persistence.workflow_transaction import load_workflow_chapter
from aiwebnovel.project.identifiers import ProjectId


class ChapterPlanRevisionRecord(Base):
    __tablename__ = "chapter_plan_revisions"
    __table_args__ = (
        UniqueConstraint("chapter_id", "version", name="uq_chapter_plan_revision_version"),
        CheckConstraint("version > 0", name="ck_chapter_plan_version"),
        Index("ix_chapter_plan_chapter", "chapter_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chapter_id: Mapped[ChapterId] = mapped_column(
        PrefixedUlidType(ChapterId), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChapterPlanningRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _current(session: Session, chapter_id: str) -> ChapterPlanRevisionRecord | None:
        return session.scalar(
            select(ChapterPlanRevisionRecord)
            .where(ChapterPlanRevisionRecord.chapter_id == ChapterId.parse(chapter_id))
            .order_by(ChapterPlanRevisionRecord.version.desc())
            .limit(1)
        )

    @staticmethod
    def _snapshot(record: ChapterPlanRevisionRecord) -> ChapterPlan:
        return ChapterPlan(
            **record.payload,
            chapter_id=str(record.chapter_id),
            project_id=str(record.project_id),
            version=record.version,
            revision_id=record.id,
            updated_at=record.created_at.replace(tzinfo=UTC).isoformat(),
        )

    def get(self, chapter_id: str) -> ChapterPlan | None:
        with self._session_factory() as session:
            load_workflow_chapter(session, chapter_id)
            current = self._current(session, chapter_id)
            return None if current is None else self._snapshot(current)

    def save(self, chapter_id: str, document: SaveChapterPlan) -> ChapterPlan:
        with self._session_factory() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            chapter = load_workflow_chapter(session, chapter_id)
            current = self._current(session, chapter_id)
            version = 0 if current is None else current.version
            if document.expected_version != version:
                raise PlanningConflict
            record = ChapterPlanRevisionRecord(
                id=str(uuid4()),
                chapter_id=chapter.chapter.id,
                project_id=chapter.chapter.project_id,
                version=version + 1,
                created_at=datetime.now(UTC),
                payload=document.model_dump(exclude={"expected_version"}),
            )
            session.add(record)
            session.flush()
            result = self._snapshot(record)
            session.commit()
            return result
