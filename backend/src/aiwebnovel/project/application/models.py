"""Stable Project application read models made only from boundary-safe values."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    """Detached representation of one Project and its current immutable revision."""

    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime
    head_updated_at: datetime


__all__ = ["ProjectSnapshot"]
