"""Own the story control storage adapter; importing this factory never registers ORM models."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.story_control.service import StoryControlService
from aiwebnovel.story_memory.service import StoryMemoryService


def compose_story_control(
    sessions: Callable[[], Session],
    projects: ProjectQueryService,
    structure: NovelStructureQueryService,
    characters: CharacterQueryService,
    memory: StoryMemoryService,
) -> StoryControlService:
    from aiwebnovel.story_control.persistence import SqlAlchemyStoryControlRepository

    return StoryControlService(
        SqlAlchemyStoryControlRepository(sessions, projects), structure, characters, memory
    )
