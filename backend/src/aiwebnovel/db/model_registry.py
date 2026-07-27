"""Deterministic registration of authorized SQLAlchemy business models."""

from sqlalchemy import MetaData

from aiwebnovel.db.base import Base

PROJECT_TABLE_NAMES = frozenset({"projects", "project_revisions", "project_heads"})
STORY_BIBLE_TABLE_NAMES = frozenset(
    {
        "story_bibles",
        "story_bible_revisions",
        "story_bible_heads",
    }
)
BUSINESS_TABLE_NAMES = PROJECT_TABLE_NAMES | STORY_BIBLE_TABLE_NAMES


def load_model_metadata() -> MetaData:
    """Load the explicit model set without connecting to or migrating a database."""
    from aiwebnovel.project.persistence.models import (
        ProjectHeadRecord,
        ProjectRecord,
        ProjectRevisionRecord,
    )
    from aiwebnovel.story_bible.persistence.models import (
        StoryBibleHeadRecord,
        StoryBibleRecord,
        StoryBibleRevisionRecord,
    )

    registered_records = (
        ProjectRecord,
        ProjectRevisionRecord,
        ProjectHeadRecord,
        StoryBibleRecord,
        StoryBibleRevisionRecord,
        StoryBibleHeadRecord,
    )
    if any(record.metadata is not Base.metadata for record in registered_records):
        raise RuntimeError("Registered models must use the shared database metadata")
    if frozenset(Base.metadata.tables) != BUSINESS_TABLE_NAMES:
        raise RuntimeError("Registered database model tables do not match the authorized set")
    return Base.metadata
