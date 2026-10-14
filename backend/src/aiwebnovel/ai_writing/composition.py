"""Bind providers and persistent workflows at the composition boundary."""

from collections.abc import Callable

from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.application.context import ChapterWritingContextBuilder
from aiwebnovel.ai_writing.application.models import GeneratedText, GenerationMessage
from aiwebnovel.ai_writing.application.services import AIWritingService
from aiwebnovel.ai_writing.application.workflow import AIWorkflowService
from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot
from aiwebnovel.ai_writing.errors import AIWorkflowSchemaRequired
from aiwebnovel.ai_writing.provider import LocalOpenAICompatibleProvider
from aiwebnovel.ai_writing.runtime import WorkflowRuntimeLock
from aiwebnovel.chapter_planning.service import ChapterPlanningService
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.core.config import Settings
from aiwebnovel.db.engine import database_file_path
from aiwebnovel.model_gateway.service import ModelGatewayService
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.storage.paths import StoragePaths
from aiwebnovel.story_bible.application.services import StoryBibleQueryService
from aiwebnovel.writing_studio.application.service import WritingStudioService
from aiwebnovel.writing_studio.composition import compose_writing_studio


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


def compose_ai_workflow(
    settings: Settings,
    storage_paths: StoragePaths,
    engine: Engine,
    session_factory: Callable[[], Session],
    structure: NovelStructureQueryService,
    projects: ProjectQueryService,
    story_bibles: StoryBibleQueryService,
    characters: CharacterQueryService,
) -> (
    tuple[
        AIWorkflowService,
        ModelGatewayService,
        WorkflowRuntimeLock,
        WritingStudioService,
        ChapterPlanningService,
    ]
    | None
):
    # Runtime composition must not create or migrate an empty database. The launcher
    # initializes its schema explicitly; readiness owns the first connection otherwise.
    database_path = database_file_path(engine.url)
    if database_path is None or not database_path.is_file():
        return None
    if not {
        "ai_workflow_runs",
        "ai_workflow_candidates",
        "writing_references",
        "writing_rule_versions",
        "chapter_plan_revisions",
    } <= set(inspect(engine).get_table_names()):
        raise AIWorkflowSchemaRequired
    from aiwebnovel.ai_writing.persistence.repository import SqlAlchemyWorkflowRepository

    runtime = WorkflowRuntimeLock(storage_paths.runtime_locks)
    if not runtime.acquire():
        return None
    try:
        gateway = ModelGatewayService(
            storage_paths.root,
            default_base_url=settings.ai_base_url,
            default_model=settings.ai_model,
        )

        def generate(
            profile_id: str | None,
            messages: tuple[GenerationMessage, ...],
            max_output: int,
            model_snapshot: ModelSnapshot | None,
        ) -> GeneratedText:
            # Character and provider-token budgets are distinct, both bounded.
            expected = (
                None
                if model_snapshot is None
                else (
                    model_snapshot.kind,
                    model_snapshot.base_url,
                    model_snapshot.model,
                    model_snapshot.max_output_tokens,
                )
            )
            return gateway.generate(
                profile_id or "default-local", messages, expected_configuration=expected
            )

        def read_model(profile_id: str | None) -> ModelSnapshot:
            profile = gateway.get_profile(profile_id or "default-local")
            return ModelSnapshot(
                profile.id,
                profile.name,
                profile.kind,
                profile.base_url,
                profile.model,
                profile.max_output_tokens,
            )

        studio, planning = compose_writing_studio(
            session_factory, structure, projects, characters, story_bibles, generate, read_model
        )
        service = AIWorkflowService(
            SqlAlchemyWorkflowRepository(session_factory),
            ChapterWritingContextBuilder(
                structure, projects, story_bibles, characters, planning.context_sources
            ),
            structure,
            generate,
            read_model,
        )
        service.recover_interrupted()
        return service, gateway, runtime, studio, planning
    except BaseException:
        runtime.close()
        raise
