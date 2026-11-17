"""Immutable source anchors, model analysis and author-confirmed rules."""

from dataclasses import dataclass
from typing import Literal, Protocol

from aiwebnovel.ai_writing.application.models import GenerationMessage
from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot
from aiwebnovel.domain.errors import DomainError


class WritingInputInvalid(DomainError):
    message = "Reference study input is invalid or exceeds its bounded limits."


class WritingNotFound(DomainError):
    message = "The reference or writing rule was not found in this project."


class WritingConflict(DomainError):
    message = "The reference or rule changed; refresh before continuing."


class WritingOutputInvalid(DomainError):
    message = "The analysis must cover every source unit with valid anchored evidence."


class WritingConsentRequired(DomainError):
    message = "Confirm sending this reference to the selected cloud model."


@dataclass(frozen=True, slots=True)
class ReferenceUnit:
    id: str
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class WritingRule:
    name: str
    instruction: str
    applies_to: str
    scene_tags: tuple[str, ...] = ()
    excludes: str = ""
    priority: int = 3


@dataclass(frozen=True, slots=True)
class UnitAnalysis:
    unit_id: str
    quote: str
    function: str
    effect: str
    rationale: str
    transfer: str


@dataclass(frozen=True, slots=True)
class ReferenceAnalysis:
    units: tuple[UnitAnalysis, ...]
    long_form_notes: str
    rules: tuple[WritingRule, ...]


@dataclass(frozen=True, slots=True)
class WritingReference:
    id: str
    project_id: str
    title: str
    text: str
    granularity: Literal["sentence", "paragraph"]
    units: tuple[ReferenceUnit, ...]
    model_snapshot: ModelSnapshot
    messages: tuple[GenerationMessage, ...]
    status: Literal["ready", "analyzing", "analyzed", "failed"]
    version: int
    attempts: int
    last_error: str | None
    analysis: ReferenceAnalysis | None
    created_at: str


@dataclass(frozen=True, slots=True)
class WritingRuleVersion:
    id: str
    rule_id: str
    project_id: str
    version: int
    title: str
    reference_id: str | None
    rules: tuple[WritingRule, ...]
    created_at: str
    template_source_id: str | None = None
    template_source_rule_version_id: str | None = None
    template_source_rule_index: int | None = None


class WritingRepository(Protocol):
    def create_reference(self, reference: WritingReference) -> WritingReference: ...

    def get_reference(self, project_id: str, reference_id: str) -> WritingReference: ...

    def list_references(self, project_id: str) -> tuple[WritingReference, ...]: ...

    def claim(self, project_id: str, reference_id: str, version: int) -> WritingReference: ...

    def finish(
        self, project_id: str, reference_id: str, analysis: ReferenceAnalysis
    ) -> WritingReference: ...

    def fail(self, project_id: str, reference_id: str, error: str) -> None: ...

    def recover_interrupted(self) -> None: ...

    def save_rules(
        self, rules: WritingRuleVersion, expected_version: int | None
    ) -> WritingRuleVersion: ...

    def list_rules(self, project_id: str) -> tuple[WritingRuleVersion, ...]: ...

    def get_rules(
        self, project_id: str, version_ids: tuple[str, ...]
    ) -> tuple[WritingRuleVersion, ...]: ...
