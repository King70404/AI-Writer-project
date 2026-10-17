"""Immutable memory revisions with ownership and source checks under a writer lock."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.novel_structure.identifiers import ChapterId
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_memory.models import Fact, MemoryConflict, MemoryItem, Review


class StoryMemoryRevisionRecord(Base):
    __tablename__ = "story_memory_revisions"
    __table_args__ = (
        UniqueConstraint("entity_id", "version", name="uq_story_memory_version"),
        CheckConstraint("version > 0", name="ck_story_memory_version"),
        Index("ix_story_memory_project", "project_id", "entity_id", "version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_id: Mapped[ChapterId] = mapped_column(
        PrefixedUlidType(ChapterId), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SqlAlchemyMemoryRepository:
    def __init__(self, sessions: Callable[[], Session], projects: ProjectQueryService) -> None:
        self._sessions = sessions
        self._projects = projects

    def recover_interrupted(self) -> None:
        with self._sessions() as session:
            project_ids = session.scalars(
                select(StoryMemoryRevisionRecord.project_id).distinct()
            ).all()
        for project_id in project_ids:
            try:
                items = self.list(str(project_id))
                for item in items:
                    if isinstance(item, Review) and item.status == "running":
                        updated = item.model_copy(
                            update={
                                "revision_id": str(uuid4()),
                                "version": item.version + 1,
                                "status": "failed",
                                "last_error": "AIProviderUnavailable",
                                "updated_at": datetime.now(UTC).isoformat(),
                            }
                        )
                        self.save(updated, item.version, lambda: None)
            except ProjectNotFound:
                continue

    def list(self, project_id: str) -> tuple[MemoryItem, ...]:
        if self._projects.get_project(GetProjectQuery(project_id)) is None:
            raise ProjectNotFound(ProjectId.parse(project_id))
        record = StoryMemoryRevisionRecord
        latest = (
            select(record.entity_id, func.max(record.version).label("version"))
            .where(record.project_id == ProjectId.parse(project_id))
            .group_by(record.entity_id)
            .subquery()
        )
        with self._sessions() as session:
            rows = session.scalars(
                select(record)
                .join(
                    latest,
                    (record.entity_id == latest.c.entity_id) & (record.version == latest.c.version),
                )
                .order_by(record.entity_id)
            )
            return tuple(
                (Fact if row.payload["kind"] == "fact" else Review).model_validate(row.payload)
                for row in rows
            )

    def save(
        self, item: MemoryItem, expected_version: int, validate: Callable[[], None]
    ) -> MemoryItem:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            if self._projects.get_project(GetProjectQuery(item.project_id)) is None:
                raise ProjectNotFound(ProjectId.parse(item.project_id))
            validate()
            record = StoryMemoryRevisionRecord
            current = session.scalar(
                select(record)
                .where(record.entity_id == item.id)
                .order_by(record.version.desc())
                .limit(1)
            )
            if (0 if current is None else current.version) != expected_version:
                raise MemoryConflict
            if current is not None and (
                str(current.project_id) != item.project_id
                or str(current.chapter_id) != item.chapter_id
                or current.payload["kind"] != item.kind
            ):
                raise MemoryConflict
            session.add(
                record(
                    id=item.revision_id,
                    entity_id=item.id,
                    project_id=ProjectId.parse(item.project_id),
                    chapter_id=ChapterId.parse(item.chapter_id),
                    version=item.version,
                    payload=item.model_dump(),
                )
            )
            session.commit()
        return item
