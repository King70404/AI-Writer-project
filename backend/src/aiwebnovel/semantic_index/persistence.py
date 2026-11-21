"""Semantic index rows: derived, replaceable vectors plus append-only settings revisions.

Entries are a cache of what a confirmed build returned: an incremental build replaces
the rows it re-embedded and deletes rows whose source no longer qualifies. Settings are
append-only revisions guarded by an expected version. No text is stored, only hashes.
"""

import struct
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.semantic_index.models import (
    Entry,
    EntryKind,
    SemanticIndexConflict,
    SemanticIndexInvalid,
    Settings,
)

MAX_DIMENSIONS = 8192


class SemanticIndexEntryRecord(Base):
    __tablename__ = "semantic_index_entries"
    __table_args__ = (
        CheckConstraint("kind IN ('fact','chapter_chunk')", name="ck_semantic_entry_kind"),
        CheckConstraint("dimensions BETWEEN 1 AND 8192", name="ck_semantic_entry_dimensions"),
        UniqueConstraint("project_id", "kind", "source_id", name="uq_semantic_entry_source"),
        Index("ix_semantic_entry_project", "project_id", "kind"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    chapter_id: Mapped[str] = mapped_column(String(60), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(60), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class SemanticIndexSettingsRecord(Base):
    __tablename__ = "semantic_index_settings"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_semantic_settings_version"),
        CheckConstraint(
            "enabled IN (0, 1) AND (enabled = 0 OR profile_id IS NOT NULL)",
            name="ck_semantic_settings_enabled",
        ),
        UniqueConstraint("project_id", "version", name="uq_semantic_settings_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


def encode(vector: tuple[float, ...]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def decode(data: bytes, dimensions: int) -> tuple[float, ...]:
    if len(data) != dimensions * 4:
        raise SemanticIndexInvalid
    return struct.unpack(f"<{dimensions}f", data)


def _entry(record: SemanticIndexEntryRecord) -> Entry:
    kind: EntryKind = "fact" if record.kind == "fact" else "chapter_chunk"
    return Entry(
        kind,
        record.source_id,
        record.chapter_id,
        record.source_revision,
        record.profile_id,
        record.config_hash,
        record.text_hash,
        decode(record.vector, record.dimensions),
    )


class SqlAlchemySemanticIndexStore:
    def __init__(self, sessions: Callable[[], Session], projects: ProjectQueryService) -> None:
        self._sessions = sessions
        self._projects = projects

    def _visible(self, project_id: str) -> ProjectId:
        identifier = ProjectId.parse(project_id)
        if self._projects.get_project(GetProjectQuery(project_id)) is None:
            raise ProjectNotFound(identifier)
        return identifier

    def settings(self, project_id: str) -> Settings:
        identifier = ProjectId.parse(project_id)
        with self._sessions() as session:
            record = session.scalar(
                select(SemanticIndexSettingsRecord)
                .where(SemanticIndexSettingsRecord.project_id == identifier)
                .order_by(SemanticIndexSettingsRecord.version.desc())
                .limit(1)
            )
        if record is None:
            return Settings(0, False, None, None)
        return Settings(record.version, bool(record.enabled), record.profile_id, record.created_at)

    def save_settings(
        self, project_id: str, expected_version: int, enabled: bool, profile_id: str | None
    ) -> Settings:
        identifier = self._visible(project_id)
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            current = session.scalar(
                select(SemanticIndexSettingsRecord.version)
                .where(SemanticIndexSettingsRecord.project_id == identifier)
                .order_by(SemanticIndexSettingsRecord.version.desc())
                .limit(1)
            )
            if (current or 0) != expected_version:
                session.rollback()
                raise SemanticIndexConflict
            now = datetime.now(UTC).isoformat()
            session.add(
                SemanticIndexSettingsRecord(
                    id=str(uuid4()),
                    project_id=identifier,
                    version=expected_version + 1,
                    enabled=int(enabled),
                    profile_id=profile_id,
                    created_at=now,
                )
            )
            session.commit()
        return Settings(expected_version + 1, enabled, profile_id, now)

    def entries(self, project_id: str) -> tuple[Entry, ...]:
        identifier = ProjectId.parse(project_id)
        with self._sessions() as session:
            return tuple(
                _entry(record)
                for record in session.scalars(
                    select(SemanticIndexEntryRecord)
                    .where(SemanticIndexEntryRecord.project_id == identifier)
                    .order_by(SemanticIndexEntryRecord.kind, SemanticIndexEntryRecord.source_id)
                )
            )

    def replace(self, project_id: str, entries: Iterable[Entry]) -> int:
        """Upsert one embedded batch atomically; earlier batches stay committed."""
        identifier = self._visible(project_id)
        written = 0
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            now = datetime.now(UTC).isoformat()
            for entry in entries:
                if not 1 <= len(entry.vector) <= MAX_DIMENSIONS:
                    session.rollback()
                    raise SemanticIndexInvalid
                session.execute(
                    delete(SemanticIndexEntryRecord).where(
                        SemanticIndexEntryRecord.project_id == identifier,
                        SemanticIndexEntryRecord.kind == entry.kind,
                        SemanticIndexEntryRecord.source_id == entry.source_id,
                    )
                )
                session.add(
                    SemanticIndexEntryRecord(
                        id=str(uuid4()),
                        project_id=identifier,
                        kind=entry.kind,
                        source_id=entry.source_id,
                        chapter_id=entry.chapter_id,
                        source_revision=entry.source_revision,
                        profile_id=entry.profile_id,
                        config_hash=entry.config_hash,
                        text_hash=entry.text_hash,
                        dimensions=len(entry.vector),
                        vector=encode(entry.vector),
                        created_at=now,
                    )
                )
                written += 1
            session.commit()
        return written

    def remove(self, project_id: str, keys: Iterable[tuple[str, str]]) -> int:
        identifier = self._visible(project_id)
        removed = 0
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            for kind, source_id in keys:
                result = session.execute(
                    delete(SemanticIndexEntryRecord).where(
                        SemanticIndexEntryRecord.project_id == identifier,
                        SemanticIndexEntryRecord.kind == kind,
                        SemanticIndexEntryRecord.source_id == source_id,
                    )
                )
                removed += int(getattr(result, "rowcount", 0) or 0)
            session.commit()
        return removed
