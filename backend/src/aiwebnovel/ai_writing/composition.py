"""Bind providers and persistent workflows at the composition boundary."""

from collections.abc import Callable

from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.application.context import ChapterWritingContextBuilder
from aiwebnovel.ai_writing.application.models import ContextSource, GeneratedText, GenerationMessage
from aiwebnovel.ai_writing.application.services import AIWritingService
from aiwebnovel.ai_writing.application.workflow import AIWorkflowService
from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot
from aiwebnovel.ai_writing.errors import AIProviderNotConfigured, AIWorkflowSchemaRequired
from aiwebnovel.ai_writing.runtime import WorkflowRuntimeLock
from aiwebnovel.chapter_planning.service import ChapterPlanningService
from aiwebnovel.character.application.services import CharacterQueryService
from aiwebnovel.core.config import Settings
from aiwebnovel.db.engine import database_file_path
from aiwebnovel.model_gateway.errors import ModelProfileNotFound
from aiwebnovel.model_gateway.service import ModelGatewayService
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.storage.paths import StoragePaths
from aiwebnovel.story_bible.application.services import StoryBibleQueryService
from aiwebnovel.story_control.composition import compose_story_control
from aiwebnovel.story_control.service import StoryControlService
from aiwebnovel.story_memory.composition import compose_story_memory
from aiwebnovel.story_memory.service import StoryMemoryService
from aiwebnovel.usage.budget_service import UsageBudgetService
from aiwebnovel.usage.composition import compose_usage_ledger
from aiwebnovel.usage.models import UsageLedgerUnavailable
from aiwebnovel.usage.service import UsageLedgerService
from aiwebnovel.workbench.composition import compose_workbench
from aiwebnovel.workbench.service import WorkbenchService
from aiwebnovel.writing_studio.application.service import WritingStudioService
from aiwebnovel.writing_studio.composition import compose_writing_studio


class UnmeteredSendRefused:
    """Stands in until the usage ledger is ready: legacy endpoints never send unmetered."""

    def generate(self, messages: tuple[GenerationMessage, ...]) -> GeneratedText:
        raise UsageLedgerUnavailable


class MeteredWorkflowProvider:
    """Routes legacy continue/rewrite through the workflow's metered, budgeted gateway."""

    def __init__(self, workflow: AIWorkflowService) -> None:
        self._workflow = workflow

    def generate(self, messages: tuple[GenerationMessage, ...]) -> GeneratedText:
        try:
            return self._workflow.send_text(messages)
        except ModelProfileNotFound:
            # Keep the legacy contract: no default model means "not configured".
            raise AIProviderNotConfigured from None


def compose_ai_writing(
    settings: Settings,
    structure: NovelStructureQueryService,
    projects: ProjectQueryService,
    story_bibles: StoryBibleQueryService,
    characters: CharacterQueryService,
    workflow: AIWorkflowService | None = None,
) -> AIWritingService:
    del settings  # The model endpoint comes from the gateway profile, not raw settings.
    return AIWritingService(
        ChapterWritingContextBuilder(structure, projects, story_bibles, characters),
        UnmeteredSendRefused() if workflow is None else MeteredWorkflowProvider(workflow),
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
        StoryMemoryService,
        WorkbenchService,
        UsageLedgerService,
        UsageBudgetService,
        StoryControlService,
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
        "story_memory_revisions",
        "chapter_editorial_revisions",
        "model_usage_attempts",
        "ai_candidate_edits",
        "model_budget_reservations",
        "story_control_revisions",
        "method_trials",
        "method_annotations",
        "method_templates",
        "plan_proposals",
        "foreshadow_proposals",
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
        usage, budgets = compose_usage_ledger(session_factory, projects, gateway.get_profile)
        assert budgets is not None
        usage.recover_interrupted()

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
            # Every request that leaves the process is recorded under the caller's
            # explicit attribution; local pre-send failures write no ledger row.
            return usage.metered(
                messages,
                lambda before_send: gateway.generate(
                    profile_id or "default-local",
                    messages,
                    expected_configuration=expected,
                    before_send=before_send,
                ),
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
            session_factory,
            structure,
            projects,
            characters,
            story_bibles,
            generate,
            read_model,
            budgets,
        )

        def generation_sources(chapter_id: str) -> tuple[ContextSource, ...]:
            return tuple(
                source
                for run in service.list(chapter_id)
                for source in run.context.manifest.sources
                if source.source == "story_memory" and source.omitted_reason is None
            )

        memory = compose_story_memory(
            session_factory,
            projects,
            structure,
            generate,
            read_model,
            generation_sources,
            lambda chapter_id: control.selection_policy(chapter_id),
        )
        control = compose_story_control(
            session_factory,
            projects,
            structure,
            characters,
            memory,
            provider=generate,
            model_reader=read_model,
            budgets=budgets,
        )

        def extra_sources(chapter_id: str) -> tuple[ContextSource, ...]:
            # Author plans are labelled guidance; confirmed facts follow the recall policy.
            return (
                planning.context_sources(chapter_id)
                + control.guide_sources(chapter_id)
                + memory.context_sources(chapter_id)
            )

        service = AIWorkflowService(
            SqlAlchemyWorkflowRepository(session_factory),
            ChapterWritingContextBuilder(
                structure, projects, story_bibles, characters, extra_sources
            ),
            structure,
            generate,
            read_model,
            budgets.estimate,
        )
        service.recover_interrupted()
        return (
            service,
            gateway,
            runtime,
            studio,
            planning,
            memory,
            compose_workbench(session_factory, projects),
            usage,
            budgets,
            control,
        )
    except BaseException:
        runtime.close()
        raise
