"""Wire reference analysis and chapter plans to the existing model gateway."""

import json
from collections.abc import Callable
from dataclasses import asdict

from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.application.models import ContextSource
from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot, WorkflowProvider
from aiwebnovel.chapter_planning.service import ChapterPlanningService
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.story_bible.application.services import StoryBibleQueryService
from aiwebnovel.usage.budget_service import UsageBudgetService
from aiwebnovel.writing_studio.application.method_service import MethodService
from aiwebnovel.writing_studio.application.service import WritingStudioService


def compose_writing_studio(
    session_factory: Callable[[], Session],
    structure: NovelStructureQueryService,
    projects: ProjectQueryService,
    characters: CharacterQueryService,
    story_bibles: StoryBibleQueryService,
    provider: WorkflowProvider,
    model_reader: Callable[[str | None], ModelSnapshot],
    budgets: UsageBudgetService,
) -> tuple[WritingStudioService, ChapterPlanningService]:
    # Persistence models are registered only during explicit runtime composition,
    # never as a side effect of importing the application or its routers.
    from aiwebnovel.chapter_planning.persistence import ChapterPlanningRepository
    from aiwebnovel.writing_studio.persistence.method_repository import MethodRepository
    from aiwebnovel.writing_studio.persistence.repository import SqlAlchemyWritingRepository

    studio = WritingStudioService(
        SqlAlchemyWritingRepository(session_factory, projects), provider, model_reader
    )
    studio.recover_interrupted()

    def rule_sources(project_id: str, revision_ids: tuple[str, ...]) -> tuple[ContextSource, ...]:
        versions = studio.get_rules(project_id, revision_ids)
        sources = []
        remaining = 8_000
        for version in versions:
            # Only confirmed methods enter manuscript generation, never the
            # reference's original prose, analysis prompt or model commentary.
            original = json.dumps(
                {"title": version.title, "rules": [asdict(rule) for rule in version.rules]},
                ensure_ascii=False,
            )
            text = original[:remaining]
            sources.append(
                ContextSource(
                    "writing_rules",
                    ((version.rule_id, version.id),),
                    text,
                    f"作者选用的写作规则第 {version.version} 版",
                    "写作规则上下文预算已用完" if not text else None,
                    len(text) != len(original),
                )
            )
            remaining -= len(text)
        return tuple(sources)

    planning = ChapterPlanningService(
        ChapterPlanningRepository(session_factory),
        structure,
        characters,
        story_bibles,
        studio.get_rules,
        rule_sources,
    )
    method_store = MethodRepository(session_factory, projects)
    method_store.recover_interrupted()
    studio.method_service = MethodService(
        method_store, structure, planning, studio, provider, model_reader, budgets
    )
    return studio, planning
