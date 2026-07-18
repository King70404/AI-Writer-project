"""Deterministic registration of authorized SQLAlchemy business models."""

from sqlalchemy import MetaData

from aiwebnovel.db.base import Base

PROJECT_TABLE_NAMES = frozenset({"projects", "project_revisions", "project_heads"})


def load_model_metadata() -> MetaData:
    """Load the explicit model set without connecting to or migrating a database."""
    from aiwebnovel.project.persistence.models import (
        ProjectHeadRecord,
        ProjectRecord,
        ProjectRevisionRecord,
    )

    registered_records = (ProjectRecord, ProjectRevisionRecord, ProjectHeadRecord)
    if any(record.metadata is not Base.metadata for record in registered_records):
        raise RuntimeError("Registered models must use the shared database metadata")
    if frozenset(Base.metadata.tables) != PROJECT_TABLE_NAMES:
        raise RuntimeError("Registered database model tables do not match the authorized set")
    return Base.metadata
