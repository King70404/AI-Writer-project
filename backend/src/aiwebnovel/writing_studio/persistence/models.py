"""Reference drafts never write chapter content or automatically activate methods."""

from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.project.identifiers import ProjectId


class WritingReferenceRecord(Base):
    __tablename__ = "writing_references"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_writing_references_version"),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="ck_writing_references_attempts"),
        CheckConstraint(
            "status IN ('ready','analyzing','analyzed','failed')",
            name="ck_writing_references_status",
        ),
        Index("ix_writing_references_project", "project_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class WritingRuleVersionRecord(Base):
    __tablename__ = "writing_rule_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_writing_rule_versions_version"),
        UniqueConstraint("rule_id", "version", name="uq_writing_rule_versions_number"),
        Index("ix_writing_rule_versions_project", "project_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    reference_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("writing_references.id", ondelete="RESTRICT"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
