"""Persistent previews and idempotent receipts for manuscript imports."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aiwebnovel.db.base import Base


class ImportPreviewRecord(Base):
    __tablename__ = "import_previews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    chapters: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ImportReceiptRecord(Base):
    __tablename__ = "import_receipts"
    __table_args__ = (UniqueConstraint("preview_id", name="uq_import_receipt_preview"),)
    idempotency_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(30), nullable=False)
    first_chapter_id: Mapped[str] = mapped_column(String(30), nullable=False)
