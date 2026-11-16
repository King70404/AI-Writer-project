"""F08 trial snapshots, manual annotations and author-written templates."""

from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.project.identifiers import ProjectId


class MethodTrialRecord(Base):
    __tablename__ = "method_trials"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_method_trial_version"),
        Index("ix_method_trial_project", "project_id", "chapter_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    rule_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("writing_rule_versions.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MethodAnnotationRecord(Base):
    __tablename__ = "method_annotations"
    __table_args__ = (Index("ix_method_annotation_project", "project_id", "chapter_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    rule_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("writing_rule_versions.id", ondelete="RESTRICT"), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MethodTemplateRecord(Base):
    __tablename__ = "method_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
