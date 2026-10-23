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
AI_WORKFLOW_TABLE_NAMES = frozenset({"ai_workflow_runs", "ai_workflow_candidates"})
WRITING_STUDIO_TABLE_NAMES = frozenset(
    {"writing_references", "writing_rule_versions", "chapter_plan_revisions"}
)
STORY_MEMORY_TABLE_NAMES = frozenset({"story_memory_revisions"})
WORKBENCH_TABLE_NAMES = frozenset({"chapter_editorial_revisions"})
BUSINESS_TABLE_NAMES = (
    PROJECT_TABLE_NAMES
    | STORY_BIBLE_TABLE_NAMES
    | CHARACTER_TABLE_NAMES
    | NOVEL_STRUCTURE_TABLE_NAMES
    | AI_WORKFLOW_TABLE_NAMES
    | WRITING_STUDIO_TABLE_NAMES
    | STORY_MEMORY_TABLE_NAMES
    | WORKBENCH_TABLE_NAMES
)


def load_model_metadata() -> MetaData:
    """Load the explicit model set without connecting to or migrating a database."""
    from aiwebnovel.ai_writing.persistence.models import (
        AIWorkflowCandidateRecord,
        AIWorkflowRunRecord,
    )
    from aiwebnovel.chapter_planning.persistence import ChapterPlanRevisionRecord
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
    from aiwebnovel.story_memory.persistence import StoryMemoryRevisionRecord
    from aiwebnovel.workbench.persistence import ChapterEditorialRevisionRecord
    from aiwebnovel.writing_studio.persistence.models import (
        WritingReferenceRecord,
        WritingRuleVersionRecord,
    )

    registered_records = (
        AIWorkflowRunRecord,
        AIWorkflowCandidateRecord,
        WritingReferenceRecord,
        WritingRuleVersionRecord,
        ChapterPlanRevisionRecord,
        StoryMemoryRevisionRecord,
        ChapterEditorialRevisionRecord,
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
