from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aiwebnovel.db.base import Base


class HandoffRecord(Base):
    __tablename__ = "handoff_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chapter_id: Mapped[str] = mapped_column(String(30), nullable=False)
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    base_revision: Mapped[str] = mapped_column(String(30), nullable=False)
    context_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)


class ExternalCandidateRecord(Base):
    __tablename__ = "external_candidates"
    __table_args__ = (UniqueConstraint("handoff_id", "text_sha256"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    handoff_id: Mapped[str] = mapped_column(String(36), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    adoption_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
