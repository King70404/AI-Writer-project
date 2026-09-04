"""Bind the real local adapter to existing public read services."""

from aiwebnovel.ai_writing.application.context import ChapterWritingContextBuilder
from aiwebnovel.ai_writing.application.services import AIWritingService
from aiwebnovel.ai_writing.provider import LocalOpenAICompatibleProvider
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.core.config import Settings
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.story_bible.application.services import StoryBibleQueryService


def compose_ai_writing(
    settings: Settings,
    structure: NovelStructureQueryService,
    projects: ProjectQueryService,
    story_bibles: StoryBibleQueryService,
    characters: CharacterQueryService,
) -> AIWritingService:
    return AIWritingService(
        ChapterWritingContextBuilder(structure, projects, story_bibles, characters),
        LocalOpenAICompatibleProvider(settings.ai_base_url, settings.ai_model),
    )
