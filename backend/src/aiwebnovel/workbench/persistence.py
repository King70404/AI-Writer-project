"""Read-only aggregate queries and append-only editorial revisions.

Character counts are computed by SQLite from each chapter's current head revision,
so manuscript text never leaves the database for a summary. Memory items are read
through ``json_extract`` projections that omit review content snapshots.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    ColumnElement,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    and_,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from aiwebnovel.ai_writing.persistence.models import AIWorkflowCandidateRecord
from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.novel_structure.identifiers import ChapterId, ChapterRevisionId
from aiwebnovel.novel_structure.persistence.models import (
    ChapterHeadRecord,
    ChapterRecord,
    ChapterRevisionRecord,
    VolumeHeadRecord,
    VolumeRecord,
    VolumeRevisionRecord,
)
from aiwebnovel.novel_structure.persistence.workflow_transaction import load_workflow_chapter
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_memory.persistence import StoryMemoryRevisionRecord
from aiwebnovel.workbench.models import (
    EditorialConflict,
    EditorialState,
    EditorialStatus,
)
from aiwebnovel.workbench.reminder_persistence import load_reminders
from aiwebnovel.workbench.snapshot import (
    ChapterRow,
    EditorialRow,
    FactReference,
    MemoryRow,
    ProjectSnapshot,
    VolumeRow,
)

# Exactly the code points for which Python ``str.isspace`` is true.
WHITESPACE_CODE_POINTS = (
    9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
    8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202,
    8232, 8233, 8239, 8287, 12288,
)  # fmt: skip


def non_whitespace_length(column: Any) -> ColumnElement[int]:
    stripped: Any = column
    for code_point in WHITESPACE_CODE_POINTS:
        stripped = func.replace(stripped, func.char(code_point), "")
    return func.length(stripped)


class ChapterEditorialRevisionRecord(Base):
    __tablename__ = "chapter_editorial_revisions"
    __table_args__ = (
        UniqueConstraint("chapter_id", "version", name="uq_chapter_editorial_version"),
        CheckConstraint("version > 0", name="ck_chapter_editorial_version"),
        CheckConstraint("status IN ('draft','review','final')", name="ck_chapter_editorial_status"),
        Index("ix_chapter_editorial_project", "project_id", "chapter_id", "version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chapter_id: Mapped[ChapterId] = mapped_column(
        PrefixedUlidType(ChapterId), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    chapter_revision_id: Mapped[ChapterRevisionId] = mapped_column(
        PrefixedUlidType(ChapterRevisionId),
        ForeignKey("chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _iso(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


def _editorial_state(
    chapter_id: str, project_id: str, head_revision: str, row: EditorialRow | None
) -> EditorialState:
    if row is None:
        return EditorialState(
            chapter_id=chapter_id,
            project_id=project_id,
            status="draft",
            version=0,
            chapter_revision_id=None,
            content_changed=False,
            updated_at=None,
        )
    return EditorialState(
        chapter_id=chapter_id,
        project_id=project_id,
        status=row.status,
        version=row.version,
        chapter_revision_id=row.chapter_revision_id,
        content_changed=row.chapter_revision_id != head_revision,
        updated_at=row.updated_at,
    )


class SqlAlchemyWorkbenchRepository:
    def __init__(self, sessions: Callable[[], Session], projects: ProjectQueryService) -> None:
        self._sessions = sessions
        self._projects = projects

    def bookshelf(
        self, offset: int, limit: int
    ) -> tuple[int, list[tuple[str, str, ProjectSnapshot]]]:
        """A bounded project page with a constant number of batched metadata queries."""
        total, projects = self._projects.overview_page(offset, limit)
        with self._sessions() as session:
            identifiers = tuple(ProjectId.parse(row[0]) for row in projects)
            if not identifiers:
                return total, []
            volume_owners = {
                str(row[0]): str(row[1])
                for row in session.execute(
                    select(VolumeRecord.id, VolumeRecord.project_id).where(
                        VolumeRecord.project_id.in_(identifiers)
                    )
                )
            }
            chapter_owners = {
                str(row[0]): str(row[1])
                for row in session.execute(
                    select(ChapterRecord.id, ChapterRecord.project_id).where(
                        ChapterRecord.project_id.in_(identifiers)
                    )
                )
            }
            volumes = self._volumes(session, identifiers)
            chapters = self._chapters(session, identifiers)
            editorial = self._editorial(session, identifiers)
            pending = self._pending_candidates(session, identifiers)
            memory = self._memory(session, identifiers)
            threads, budgets = load_reminders(session, identifiers)
            result = []
            for identifier, title in projects:
                project = str(identifier)
                result.append(
                    (
                        project,
                        title,
                        ProjectSnapshot(
                            volumes=tuple(
                                item for item in volumes if volume_owners[item.volume_id] == project
                            ),
                            chapters=tuple(
                                item
                                for item in chapters
                                if chapter_owners[item.chapter_id] == project
                            ),
                            editorial={
                                key: value
                                for key, value in editorial.items()
                                if chapter_owners.get(key) == project
                            },
                            pending_candidates={
                                key: value
                                for key, value in pending.items()
                                if chapter_owners.get(key) == project
                            },
                            memory=tuple(
                                item
                                for item in memory
                                if chapter_owners.get(item.chapter_id) == project
                            ),
                            threads=threads.get(project, ()),
                            budget=budgets.get(project),
                        ),
                    )
                )
            return total, result

    def snapshot(self, project_id: str) -> ProjectSnapshot:
        identifier = ProjectId.parse(project_id)
        # The project query service hides logically deleted Projects.
        if self._projects.get_project(GetProjectQuery(project_id)) is None:
            raise ProjectNotFound(identifier)
        with self._sessions() as session:
            threads, budgets = load_reminders(session, (identifier,))
            return ProjectSnapshot(
                volumes=self._volumes(session, identifier),
                chapters=self._chapters(session, identifier),
                editorial=self._editorial(session, identifier),
                pending_candidates=self._pending_candidates(session, identifier),
                memory=self._memory(session, identifier),
                threads=threads.get(project_id, ()),
                budget=budgets.get(project_id),
            )

    @staticmethod
    def _volumes(
        session: Session, project_id: ProjectId | tuple[ProjectId, ...]
    ) -> tuple[VolumeRow, ...]:
        rows = session.execute(
            select(VolumeRecord.id, VolumeRevisionRecord.title, VolumeRecord.current_position)
            .join(VolumeHeadRecord, VolumeHeadRecord.volume_id == VolumeRecord.id)
            .join(
                VolumeRevisionRecord,
                and_(
                    VolumeRevisionRecord.volume_id == VolumeHeadRecord.volume_id,
                    VolumeRevisionRecord.id == VolumeHeadRecord.revision_id,
                ),
            )
            .where(
                VolumeRecord.project_id.in_(
                    project_id if isinstance(project_id, tuple) else (project_id,)
                )
            )
            .order_by(VolumeRecord.current_position, VolumeRecord.id)
        )
        return tuple(VolumeRow(str(row[0]), row[1], row[2]) for row in rows)

    @staticmethod
    def _chapters(
        session: Session, project_id: ProjectId | tuple[ProjectId, ...]
    ) -> tuple[ChapterRow, ...]:
        rows = session.execute(
            select(
                ChapterRecord.id,
                ChapterRecord.volume_id,
                VolumeRecord.current_position,
                ChapterRecord.current_position,
                ChapterRevisionRecord.title,
                ChapterRevisionRecord.id,
                ChapterHeadRecord.updated_at,
                non_whitespace_length(ChapterRevisionRecord.content),
            )
            .join(VolumeRecord, VolumeRecord.id == ChapterRecord.volume_id)
            .join(ChapterHeadRecord, ChapterHeadRecord.chapter_id == ChapterRecord.id)
            .join(
                ChapterRevisionRecord,
                and_(
                    ChapterRevisionRecord.chapter_id == ChapterHeadRecord.chapter_id,
                    ChapterRevisionRecord.id == ChapterHeadRecord.revision_id,
                ),
            )
            .where(
                ChapterRecord.project_id.in_(
                    project_id if isinstance(project_id, tuple) else (project_id,)
                ),
                VolumeRecord.project_id == ChapterRecord.project_id,
            )
            .order_by(
                VolumeRecord.current_position,
                VolumeRecord.id,
                ChapterRecord.current_position,
                ChapterRecord.id,
            )
        )
        return tuple(
            ChapterRow(
                chapter_id=str(row[0]),
                volume_id=str(row[1]),
                volume_position=row[2],
                position=row[3],
                title=row[4],
                revision_id=str(row[5]),
                updated_at=_iso(row[6]),
                characters=int(row[7]),
            )
            for row in rows
        )

    @staticmethod
    def _editorial(
        session: Session, project_id: ProjectId | tuple[ProjectId, ...]
    ) -> dict[str, EditorialRow]:
        record = ChapterEditorialRevisionRecord
        latest = (
            select(record.chapter_id, func.max(record.version).label("version"))
            .where(
                record.project_id.in_(
                    project_id if isinstance(project_id, tuple) else (project_id,)
                )
            )
            .group_by(record.chapter_id)
            .subquery()
        )
        rows = session.scalars(
            select(record).join(
                latest,
                and_(record.chapter_id == latest.c.chapter_id, record.version == latest.c.version),
            )
        )
        return {
            str(row.chapter_id): SqlAlchemyWorkbenchRepository._editorial_row(row) for row in rows
        }

    @staticmethod
    def _editorial_row(row: ChapterEditorialRevisionRecord) -> EditorialRow:
        # The table CHECK constraint admits only the three editorial states.
        status = cast(EditorialStatus, row.status)
        return EditorialRow(status, row.version, str(row.chapter_revision_id), _iso(row.created_at))

    @staticmethod
    def _pending_candidates(
        session: Session, project_id: ProjectId | tuple[ProjectId, ...]
    ) -> dict[str, int]:
        record = AIWorkflowCandidateRecord
        rows = session.execute(
            select(record.chapter_id, func.count())
            .join(ChapterRecord, ChapterRecord.id == record.chapter_id)
            .where(
                ChapterRecord.project_id.in_(
                    project_id if isinstance(project_id, tuple) else (project_id,)
                ),
                record.status == "pending",
            )
            .group_by(record.chapter_id)
        )
        return {str(row[0]): int(row[1]) for row in rows}

    @staticmethod
    def _memory(
        session: Session, project_id: ProjectId | tuple[ProjectId, ...]
    ) -> tuple[MemoryRow, ...]:
        record = StoryMemoryRevisionRecord
        latest = (
            select(record.entity_id, func.max(record.version).label("version"))
            .where(
                record.project_id.in_(
                    project_id if isinstance(project_id, tuple) else (project_id,)
                )
            )
            .group_by(record.entity_id)
            .subquery()
        )

        def field(name: str) -> Any:
            return func.json_extract(record.payload, f"$.{name}")

        rows = session.execute(
            select(
                record.entity_id,
                record.chapter_id,
                field("kind"),
                field("status"),
                field("source_revision"),
                field("revision_id"),
                field("updated_at"),
                func.json_extract(record.payload, "$.facts"),
            )
            .join(
                latest,
                and_(record.entity_id == latest.c.entity_id, record.version == latest.c.version),
            )
            .order_by(record.entity_id)
        )
        result = []
        for row in rows:
            facts = json.loads(row[7]) if isinstance(row[7], str) else []
            result.append(
                MemoryRow(
                    entity_id=row[0],
                    chapter_id=str(row[1]),
                    kind=str(row[2]),
                    status=str(row[3]),
                    source_revision=str(row[4]),
                    revision_id=str(row[5]),
                    updated_at=str(row[6]),
                    facts=tuple(
                        FactReference(
                            str(item["id"]), str(item["revision_id"]), str(item["chapter_id"])
                        )
                        for item in facts
                    ),
                )
            )
        return tuple(result)

    @staticmethod
    def _latest_editorial(session: Session, chapter_id: ChapterId) -> EditorialRow | None:
        record = ChapterEditorialRevisionRecord
        row = session.scalar(
            select(record)
            .where(record.chapter_id == chapter_id)
            .order_by(record.version.desc())
            .limit(1)
        )
        return None if row is None else SqlAlchemyWorkbenchRepository._editorial_row(row)

    def get_editorial(self, chapter_id: str) -> EditorialState:
        with self._sessions() as session:
            chapter = load_workflow_chapter(session, chapter_id)
            return _editorial_state(
                str(chapter.chapter.id),
                str(chapter.chapter.project_id),
                str(chapter.head.revision_id),
                self._latest_editorial(session, chapter.chapter.id),
            )

    def save_editorial(
        self, chapter_id: str, status: EditorialStatus, expected_version: int
    ) -> EditorialState:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            chapter = load_workflow_chapter(session, chapter_id)
            current = self._latest_editorial(session, chapter.chapter.id)
            if (0 if current is None else current.version) != expected_version:
                raise EditorialConflict
            record = ChapterEditorialRevisionRecord(
                id=str(uuid4()),
                chapter_id=chapter.chapter.id,
                project_id=chapter.chapter.project_id,
                version=expected_version + 1,
                status=status,
                chapter_revision_id=chapter.head.revision_id,
                created_at=datetime.now(UTC),
            )
            session.add(record)
            session.flush()
            state = _editorial_state(
                str(chapter.chapter.id),
                str(chapter.chapter.project_id),
                str(chapter.head.revision_id),
                self._editorial_row(record),
            )
            session.commit()
            return state
