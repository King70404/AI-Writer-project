"""Writing plans persisted independently of model tasks."""

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from aiwebnovel.db.base import Base


class WritingJobRecord(Base):
    __tablename__ = "writing_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
