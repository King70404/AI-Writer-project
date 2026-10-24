"""Immutable story control revisions; every write re-validates under the SQLite writer lock."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    and_,
    func,
    literal_column,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_control.models import (
    ControlItem,
    Event,
    Goal,
    RecallPolicy,
    State,
    StoryControlConflict,
    Thread,
)

_ITEM = TypeAdapter[ControlItem](ControlItem)
_KINDS: dict[str, type[Goal | Thread | Event | State | RecallPolicy]] = {
    "goal": Goal,
    "thread": Thread,
    "event": Event,
    "state": State,
    "recall_policy": RecallPolicy,
}


class StoryControlRevisionRecord(Base):
    __tablename__ = "story_control_revisions"
    __table_args__ = (
        UniqueConstraint("kind", "entity_id", "version", name="uq_story_control_version"),
        CheckConstraint("version > 0", name="ck_story_control_version"),
        CheckConstraint(
            "kind IN ('goal','thread','event','state','recall_policy')",
            name="ck_story_control_kind",
        ),
        Index("ix_story_control_project", "project_id", "kind", "entity_id", "version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyStoryControlRepository:
    def __init__(self, sessions: Callable[[], Session], projects: ProjectQueryService) -> None:
        self._sessions = sessions
        self._projects = projects

    def _require_project(self, project_id: str) -> ProjectId:
        identifier = ProjectId.parse(project_id)
        # The project query service hides logically deleted Projects.
        if self._projects.get_project(GetProjectQuery(project_id)) is None:
            raise ProjectNotFound(identifier)
        return identifier

    @staticmethod
    def _latest(session: Session, project_id: ProjectId) -> tuple[ControlItem, ...]:
        record = StoryControlRevisionRecord
        latest = (
            select(
                record.kind,
                record.entity_id,
                func.max(record.version).label("version"),
                # Creation order: the first revision's SQLite rowid, independent of clocks.
                func.min(literal_column("story_control_revisions.rowid")).label("first"),
            )
            .where(record.project_id == project_id)
            .group_by(record.kind, record.entity_id)
            .subquery()
        )
        rows = session.scalars(
            select(record)
            .join(
                latest,
                and_(
                    record.kind == latest.c.kind,
                    record.entity_id == latest.c.entity_id,
                    record.version == latest.c.version,
                ),
            )
            .order_by(record.kind, latest.c.first)
        )
        return tuple(_KINDS[row.kind].model_validate(row.payload) for row in rows)

    def list(self, project_id: str) -> tuple[ControlItem, ...]:
        identifier = self._require_project(project_id)
        with self._sessions() as session:
            return self._latest(session, identifier)

    def save(
        self,
        item: ControlItem,
        expected_version: int,
        validate: Callable[[tuple[ControlItem, ...]], None],
    ) -> ControlItem:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            identifier = self._require_project(item.project_id)
            current_items = self._latest(session, identifier)
            entity_id = item.chapter_id if isinstance(item, RecallPolicy) else item.id
            current = next(
                (
                    existing
                    for existing in current_items
                    if existing.kind == item.kind
                    and (existing.chapter_id if isinstance(existing, RecallPolicy) else existing.id)
                    == entity_id
                ),
                None,
            )
            if (0 if current is None else current.version) != expected_version:
                raise StoryControlConflict
            validate(current_items)
            session.add(
                StoryControlRevisionRecord(
                    id=item.revision_id,
                    entity_id=entity_id,
                    kind=item.kind,
                    version=item.version,
                    project_id=identifier,
                    payload=_ITEM.dump_python(item, mode="json"),
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
        return item
