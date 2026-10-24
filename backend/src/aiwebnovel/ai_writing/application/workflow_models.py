"""Detached workflow contracts. Character budgets count non-whitespace Unicode code points."""

from dataclasses import dataclass
from typing import Literal, Protocol

from aiwebnovel.ai_writing.application.models import (
    ContextManifest,
    GeneratedText,
    GenerationMessage,
)
from aiwebnovel.domain.errors import DomainError

Operation = Literal["continue", "rewrite"]
RunStatus = Literal["ready", "generating", "paused", "interrupted", "completed"]
CandidateStatus = Literal["pending", "adopted", "discarded"]


class WorkflowConflict(DomainError):
    message = "The workflow state changed or the requested transition is unavailable."


class WorkflowNotFound(DomainError):
    message = "The AI workflow was not found."


class WorkflowOutputInvalid(DomainError):
    message = "The model must return between 200 and 300 non-whitespace characters."


@dataclass(frozen=True, slots=True)
class ContextPack:
    text: str
    sha256: str
    manifest: ContextManifest


MAX_CANDIDATE_EDITS = 50
MAX_EDIT_CHARACTERS = 3000
MAX_EDIT_LENGTH = 12_000


class CandidateEditInvalid(DomainError):
    message = "The author edit must change the text and stay within 1 to 3000 characters."


@dataclass(frozen=True, slots=True)
class CandidateEdit:
    """An immutable author revision derived from one model candidate.

    ``base_revision_id``/``base_version`` record the saved manuscript this edit was
    written against; adopting it requires that manuscript to still be current.
    """

    edit_id: str
    candidate_id: str
    sequence: int
    parent_edit_id: str | None
    text: str
    character_count: int
    base_revision_id: str
    base_version: int
    created_at: str
    source: Literal["author"] = "author"


@dataclass(frozen=True, slots=True)
class WorkflowCandidate:
    candidate_id: str
    sequence: int
    text: str
    model: str
    character_count: int
    status: CandidateStatus
    adopted_revision_id: str | None
    adopted_version: int | None
    latest_edit: CandidateEdit | None = None
    edit_count: int = 0
    adopted_edit_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModelSnapshot:
    id: str
    name: str
    kind: str
    base_url: str
    model: str
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    run_id: str
    chapter_id: str
    operation: Operation
    status: RunStatus
    base_revision_id: str
    base_version: int
    current_revision_id: str
    current_version: int
    instruction: str
    profile_id: str | None
    selected_text: str
    selection_start: int | None
    selection_end: int | None
    max_steps: int
    max_output_characters: int
    generated_steps: int
    generated_characters: int
    context: ContextPack
    candidates: tuple[WorkflowCandidate, ...]
    last_error: str | None
    model_snapshot: ModelSnapshot | None = None


class WorkflowProvider(Protocol):
    def __call__(
        self,
        profile_id: str | None,
        messages: tuple[GenerationMessage, ...],
        max_output: int,
        model_snapshot: ModelSnapshot | None,
    ) -> GeneratedText: ...


class WorkflowRepository(Protocol):
    def create(self, run: WorkflowRun) -> WorkflowRun: ...

    def get(self, chapter_id: str, run_id: str) -> WorkflowRun: ...

    def list(self, chapter_id: str) -> tuple[WorkflowRun, ...]: ...

    def claim(self, chapter_id: str, run_id: str) -> WorkflowRun: ...

    def finish(
        self, chapter_id: str, run_id: str, generated: GeneratedText, character_count: int
    ) -> WorkflowRun: ...

    def fail(self, chapter_id: str, run_id: str, error_code: str) -> None: ...

    def transition(self, chapter_id: str, run_id: str, *, resume: bool) -> WorkflowRun: ...

    def adopt(
        self,
        chapter_id: str,
        candidate_id: str,
        expected_version: int,
        idempotency_key: str,
        edit_id: str | None = None,
    ) -> WorkflowRun: ...

    def create_edit(
        self, chapter_id: str, candidate_id: str, text: str, parent_edit_id: str | None
    ) -> WorkflowRun: ...

    def list_edits(self, chapter_id: str, candidate_id: str) -> tuple[CandidateEdit, ...]: ...

    def release_unsent(self, chapter_id: str, run_id: str, error_code: str) -> None: ...

    def discard(self, chapter_id: str, candidate_id: str) -> WorkflowRun: ...

    def recover_interrupted(self) -> None: ...
