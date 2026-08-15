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
CHARACTER_TABLE_NAMES = frozenset(
    {
        "characters",
        "character_revisions",
        "character_heads",
    }
)
NOVEL_STRUCTURE_TABLE_NAMES = frozenset(
    {
        "outlines",
        "outline_revisions",
        "outline_heads",
        "volumes",
        "volume_revisions",
        "volume_heads",
        "chapters",
        "chapter_revisions",
        "chapter_heads",
    }
)
BUSINESS_TABLE_NAMES = (
    PROJECT_TABLE_NAMES
    | STORY_BIBLE_TABLE_NAMES
    | CHARACTER_TABLE_NAMES
    | NOVEL_STRUCTURE_TABLE_NAMES
)


def load_model_metadata() -> MetaData:
    """Load the explicit model set without connecting to or migrating a database."""
    from aiwebnovel.character.persistence.models import (
        CharacterHeadRecord,
        CharacterRecord,
        CharacterRevisionRecord,
    )
    from aiwebnovel.novel_structure.persistence.models import (
        ChapterHeadRecord,
        ChapterRecord,
        ChapterRevisionRecord,
        OutlineHeadRecord,
        OutlineRecord,
        OutlineRevisionRecord,
        VolumeHeadRecord,
        VolumeRecord,
        VolumeRevisionRecord,
    )
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
        CharacterRecord,
        CharacterRevisionRecord,
        CharacterHeadRecord,
        OutlineRecord,
        OutlineRevisionRecord,
        OutlineHeadRecord,
        VolumeRecord,
        VolumeRevisionRecord,
        VolumeHeadRecord,
        ChapterRecord,
        ChapterRevisionRecord,
        ChapterHeadRecord,
    )
    if any(record.metadata is not Base.metadata for record in registered_records):
        raise RuntimeError("Registered models must use the shared database metadata")
    if frozenset(Base.metadata.tables) != BUSINESS_TABLE_NAMES:
        raise RuntimeError("Registered database model tables do not match the authorized set")
    return Base.metadata
