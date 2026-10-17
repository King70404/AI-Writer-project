"""Own the memory storage adapter; importing this factory never registers ORM models."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.application.models import ContextSource
from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot, WorkflowProvider
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.story_memory.service import StoryMemoryService


def compose_story_memory(
    sessions: Callable[[], Session],
    projects: ProjectQueryService,
    structure: NovelStructureQueryService,
    provider: WorkflowProvider,
    model_reader: Callable[[str | None], ModelSnapshot],
    generation_sources: Callable[[str], tuple[ContextSource, ...]],
) -> StoryMemoryService:
    from aiwebnovel.story_memory.persistence import SqlAlchemyMemoryRepository

    repository = SqlAlchemyMemoryRepository(sessions, projects)
    repository.recover_interrupted()
    return StoryMemoryService(repository, structure, provider, model_reader, generation_sources)
