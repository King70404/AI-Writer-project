"""Author-controlled method trials using frozen sources and the metered provider."""

from collections.abc import Callable
from secrets import randbelow
from typing import Literal, Protocol
from uuid import uuid4

from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot, WorkflowProvider
from aiwebnovel.ai_writing.errors import AIProviderUnavailable
from aiwebnovel.chapter_planning.service import ChapterPlanningService
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.novel_structure.application.queries import GetChapterContentQuery
from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.usage.attribution import usage_attribution
from aiwebnovel.usage.budget import BudgetRefused, SendEstimate
from aiwebnovel.usage.budget_service import UsageBudgetService
from aiwebnovel.writing_studio.application.methods import (
    Annotation,
    Arm,
    Baseline,
    MethodTemplate,
    Rating,
    Score,
    Trial,
    annotate,
    claim,
    display,
    finish,
    messages,
    release_unsent,
    score,
    template_rule,
    validate_baseline,
)
from aiwebnovel.writing_studio.application.models import (
    WritingConflict,
    WritingConsentRequired,
    WritingInputInvalid,
    WritingNotFound,
    WritingRuleVersion,
)
from aiwebnovel.writing_studio.application.service import WritingStudioService


class MethodStore(Protocol):
    def create(self, trial: Trial) -> Trial: ...
    def get(self, project_id: str, trial_id: str) -> tuple[Trial, int]: ...
    def list_trials(self, project_id: str, chapter_id: str) -> tuple[tuple[Trial, int], ...]: ...
    def mutate(
        self,
        project_id: str,
        trial_id: str,
        expected_version: int,
        transition: Callable[[Trial], Trial],
    ) -> tuple[Trial, int]: ...
    def add_annotation(self, annotation_id: str, annotation: Annotation) -> None: ...
    def list_annotations(
        self, project_id: str, chapter_id: str
    ) -> tuple[dict[str, object], ...]: ...
    def add_template(self, template: MethodTemplate) -> None: ...
    def has_validation(self, project_id: str, rule_version_id: str, rule_index: int) -> bool: ...
    def list_templates(self) -> tuple[MethodTemplate, ...]: ...
    def get_template(self, template_id: str) -> MethodTemplate: ...
    def delete_template(self, template_id: str) -> None: ...


def _slot(trial: Trial, slot: Literal["A", "B"]) -> Arm:
    if slot not in ("A", "B"):
        raise WritingInputInvalid
    return "with" if (slot == "A") == trial.a_is_with else "without"


def _view(trial: Trial, version: int) -> dict[str, object]:
    return {
        **display(trial),
        "version": version,
        "chapter_id": trial.baseline.chapter_id,
        "manuscript_revision_id": trial.baseline.manuscript_revision_id,
        "plan_revision_id": trial.baseline.plan_revision_id,
        "rule_version_id": trial.baseline.rule_version_id,
        "rule_index": trial.baseline.rule_index,
        "scene": trial.baseline.scene,
        "plan": trial.baseline.plan,
        "manuscript": trial.baseline.manuscript,
        "method": trial.baseline.rule.instruction,
        "model_name": None if trial.model_snapshot is None else trial.model_snapshot.name,
        "model_kind": None if trial.model_snapshot is None else trial.model_snapshot.kind,
    }


class MethodService:
    def __init__(
        self,
        store: MethodStore,
        structure: NovelStructureQueryService,
        planning: ChapterPlanningService,
        writing: WritingStudioService,
        provider: WorkflowProvider,
        model_reader: Callable[[str | None], ModelSnapshot],
        budgets: UsageBudgetService,
    ) -> None:
        self._store = store
        self._structure = structure
        self._planning = planning
        self._writing = writing
        self._provider = provider
        self._models = model_reader
        self._budgets = budgets

    def prepare(
        self,
        project_id: str,
        chapter_id: str,
        *,
        manuscript_revision_id: str,
        plan_revision_id: str,
        rule_version_id: str,
        rule_index: int,
        scene_id: str,
        profile_id: str,
    ) -> dict[str, object]:
        manuscript = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        plan = self._planning.get(chapter_id)
        if manuscript.project_id != project_id or plan is None or plan.project_id != project_id:
            raise WritingNotFound
        if (
            manuscript.current_revision_id != manuscript_revision_id
            or plan.revision_id != plan_revision_id
        ):
            raise WritingConflict
        versions = self._writing.get_rules(project_id, (rule_version_id,))
        if type(rule_index) is not int or not 0 <= rule_index < len(versions[0].rules):
            raise WritingInputInvalid
        scene = next((item for item in plan.scenes if item.id == scene_id), None)
        if scene is None:
            raise WritingInputInvalid
        baseline = validate_baseline(
            Baseline(
                project_id,
                chapter_id,
                manuscript_revision_id,
                plan_revision_id,
                rule_version_id,
                scene.model_dump_json(),
                manuscript.content,
                plan.model_dump_json(),
                versions[0].rules[rule_index],
                rule_index,
            )
        )
        trial = Trial(str(uuid4()), baseline, bool(randbelow(2)), self._models(profile_id))
        self._store.create(trial)
        return _view(trial, 1)

    def get(self, project_id: str, trial_id: str) -> dict[str, object]:
        trial, version = self._store.get(project_id, trial_id)
        return _view(trial, version)

    def list(self, project_id: str, chapter_id: str) -> list[dict[str, object]]:
        manuscript = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        if manuscript.project_id != project_id:
            raise WritingNotFound
        return [
            _view(trial, version)
            for trial, version in self._store.list_trials(project_id, chapter_id)
        ]

    def estimate(self, project_id: str, trial_id: str, slot: Literal["A", "B"]) -> SendEstimate:
        trial, _ = self._store.get(project_id, trial_id)
        if trial.model_snapshot is None:
            raise WritingConflict
        _slot(trial, slot)
        # The rule-bearing arm is the longer bound for both slots. Returning the
        # exact two sizes would disclose the blind assignment before scoring.
        return self._budgets.estimate(
            chapter_id=trial.baseline.chapter_id,
            project_id=project_id,
            task_id=trial.id,
            profile_id=trial.model_snapshot.id,
            messages=messages(trial.baseline, "with"),
        )

    def send(
        self,
        project_id: str,
        trial_id: str,
        *,
        slot: Literal["A", "B"],
        expected_version: int,
        cloud_consent: bool,
    ) -> dict[str, object]:
        trial, version = self._store.get(project_id, trial_id)
        if version != expected_version or trial.model_snapshot is None:
            raise WritingConflict
        if trial.model_snapshot.kind == "cloud" and not cloud_consent:
            raise WritingConsentRequired
        model_snapshot = trial.model_snapshot
        arm = _slot(trial, slot)
        trial, version = self._store.mutate(
            project_id, trial_id, version, lambda current: claim(current, arm)
        )
        try:
            with usage_attribution(
                "method_trial",
                trial.id,
                project_id=project_id,
                chapter_id=trial.baseline.chapter_id,
            ):
                generated = self._provider(
                    model_snapshot.id,
                    messages(trial.baseline, arm),
                    12000,
                    model_snapshot,
                )
            trial, version = self._store.mutate(
                project_id,
                trial_id,
                version,
                lambda current: finish(current, arm, text=generated.text, error=None),
            )
            return _view(trial, version)
        except BudgetRefused:
            self._store.mutate(
                project_id, trial_id, version, lambda current: release_unsent(current, arm)
            )
            raise
        except Exception as error:
            code = (
                type(error).__name__ if isinstance(error, DomainError) else "AIProviderUnavailable"
            )
            self._store.mutate(
                project_id,
                trial_id,
                version,
                lambda current: finish(current, arm, text=None, error=code),
            )
            if isinstance(error, DomainError):
                raise
            raise AIProviderUnavailable from None

    def rate(
        self, project_id: str, trial_id: str, *, expected_version: int, a: Score, b: Score
    ) -> dict[str, object]:
        trial, version = self._store.mutate(
            project_id, trial_id, expected_version, lambda current: score(current, a, b)
        )
        return _view(trial, version)

    def annotate(
        self,
        project_id: str,
        chapter_id: str,
        *,
        manuscript_revision_id: str,
        rule_version_id: str,
        rule_index: int,
        start: int,
        end: int,
        judgment: Rating,
        reason: str,
    ) -> str:
        manuscript = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        if manuscript.project_id != project_id:
            raise WritingNotFound
        if manuscript.current_revision_id != manuscript_revision_id:
            raise WritingConflict
        versions = self._writing.get_rules(project_id, (rule_version_id,))
        if type(rule_index) is not int or not 0 <= rule_index < len(versions[0].rules):
            raise WritingInputInvalid
        baseline = Baseline(
            project_id,
            chapter_id,
            manuscript_revision_id,
            "manual",
            rule_version_id,
            "manual",
            manuscript.content,
            "",
            versions[0].rules[rule_index],
            rule_index,
        )
        record = annotate(baseline, start, end, judgment, reason, rule_index)
        annotation_id = str(uuid4())
        self._store.add_annotation(annotation_id, record)
        return annotation_id

    def annotations(self, project_id: str, chapter_id: str) -> tuple[dict[str, object], ...]:
        manuscript = self._structure.get_chapter_content(GetChapterContentQuery(chapter_id))
        if manuscript.project_id != project_id:
            raise WritingNotFound
        return self._store.list_annotations(project_id, chapter_id)

    def create_template(
        self,
        project_id: str,
        *,
        source_rule_version_id: str,
        source_rule_index: int,
        name: str,
        instruction: str,
        applies_to: str,
        excludes: str,
        scene_tags: tuple[str, ...],
        priority: int,
        confirmed: bool,
    ) -> MethodTemplate:
        versions = self._writing.get_rules(project_id, (source_rule_version_id,))
        if not 0 <= source_rule_index < len(versions[0].rules):
            raise WritingInputInvalid
        if not self._store.has_validation(project_id, source_rule_version_id, source_rule_index):
            raise WritingConflict
        template = MethodTemplate(
            str(uuid4()),
            project_id,
            source_rule_version_id,
            name,
            instruction,
            applies_to,
            excludes,
            scene_tags,
            priority,
            source_rule_index,
        )
        template_rule(template, confirmed=confirmed)
        self._store.add_template(template)
        return template

    def templates(self, project_id: str) -> tuple[MethodTemplate, ...]:
        self._writing.list_rules(project_id)
        return self._store.list_templates()

    def delete_template(self, project_id: str, template_id: str) -> None:
        self._writing.list_rules(project_id)
        self._store.delete_template(template_id)

    def copy_template(
        self, project_id: str, template_id: str, *, confirmed: bool
    ) -> WritingRuleVersion:
        template = self._store.get_template(template_id)
        rule = template_rule(template, confirmed=confirmed)
        return self._writing.save_rules(
            project_id,
            title=template.name,
            reference_id=None,
            rules=(rule,),
            confirmed=True,
            template_source_id=template.id,
            template_source_rule_version_id=template.source_rule_version_id,
            template_source_rule_index=template.source_rule_index,
        )
