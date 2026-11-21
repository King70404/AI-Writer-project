"""Own the semantic index storage adapter; importing never registers ORM models."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.semantic_index.service import (
    Embedder,
    Estimator,
    ProfileReader,
    SemanticIndexService,
)
from aiwebnovel.story_memory.service import StoryMemoryService


def compose_semantic_index(
    sessions: Callable[[], Session],
    projects: ProjectQueryService,
    memory: StoryMemoryService,
    structure: NovelStructureQueryService,
    profiles: ProfileReader,
    embedder: Embedder,
    estimator: Estimator,
) -> SemanticIndexService:
    from aiwebnovel.semantic_index.persistence import SqlAlchemySemanticIndexStore

    service = SemanticIndexService(
        SqlAlchemySemanticIndexStore(sessions, projects),
        memory,
        structure,
        profiles,
        embedder,
        estimator,
    )
    # Recall reads stored vectors through the ranker; it never embeds anything itself.
    memory.semantic_ranker = service.safe_rank
    memory.semantic_index = service
    return service
