"""Own the story control storage adapter; importing this factory never registers ORM models."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot, WorkflowProvider
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.story_control.service import StoryControlService
from aiwebnovel.story_memory.service import StoryMemoryService
from aiwebnovel.usage.budget_service import UsageBudgetService


def compose_story_control(
    sessions: Callable[[], Session],
    projects: ProjectQueryService,
    structure: NovelStructureQueryService,
    characters: CharacterQueryService,
    memory: StoryMemoryService,
    *,
    provider: WorkflowProvider | None = None,
    model_reader: Callable[[str | None], ModelSnapshot] | None = None,
    budgets: UsageBudgetService | None = None,
) -> StoryControlService:
    from aiwebnovel.story_control.persistence import SqlAlchemyStoryControlRepository

    service = StoryControlService(
        SqlAlchemyStoryControlRepository(sessions, projects), structure, characters, memory
    )
    if provider is not None and model_reader is not None and budgets is not None:
        from aiwebnovel.story_control.proposal_persistence import SqlAlchemyPlanProposalStore
        from aiwebnovel.story_control.proposals import PlanProposalService

        store = SqlAlchemyPlanProposalStore(sessions, projects)
        store.recover_interrupted()
        service.proposal_service = PlanProposalService(
            store, service, provider, model_reader, budgets
        )
        from aiwebnovel.story_control.foreshadow import ForeshadowExtractionService
        from aiwebnovel.story_control.foreshadow_persistence import SqlAlchemyForeshadowStore

        extractions = SqlAlchemyForeshadowStore(sessions, projects)
        extractions.recover_interrupted()
        service.foreshadow_service = ForeshadowExtractionService(
            extractions, service, provider, model_reader, budgets
        )
    return service
