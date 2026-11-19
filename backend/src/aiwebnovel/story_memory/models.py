"""Bounded persistent contracts; model suggestions never confirm story facts."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot
from aiwebnovel.domain.errors import DomainError

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,60}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Quote = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class MemoryConflict(DomainError):
    message = "Memory or its source changed. Reload before continuing."


class MemoryNotFound(DomainError):
    message = "Story memory is unavailable."


class MemoryInvalid(DomainError):
    message = "Memory input or model output is invalid."


class MemoryConsentRequired(DomainError):
    message = "Explicit consent is required for this cloud request."


class RecallPinsInvalid(DomainError):
    message = (
        "A pinned fact is no longer valid or the pinned facts exceed the recall budget. "
        "Adjust the recall policy before preparing."
    )


@dataclass(frozen=True, slots=True)
class RecallSelectionPolicy:
    """Author-chosen pinned and excluded fact ids for one chapter's generation context."""

    version: int
    pinned: tuple[str, ...]
    excluded: tuple[str, ...]


RecallMode = Literal["deterministic", "semantic", "fallback"]


@dataclass(frozen=True, slots=True)
class SemanticRanking:
    """C-4: similarity per recallable fact id, or why semantic ranking is unavailable.

    ``requested`` is the author's project setting; ``available`` is true only when the
    current chapter and every candidate fact have a valid stored vector. Producing a
    ranking reads stored vectors only and never calls a model.
    """

    requested: bool
    available: bool
    note: str | None
    similarity: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class RecallOutcome:
    facts: tuple["Fact", ...]
    selected: tuple["FrozenFact", ...]
    reasons: Mapping[str, str]
    costs: Mapping[str, int]
    omitted: tuple[tuple[str, str | None, str], ...]
    omitted_total: int
    excluded_total: int
    used: int
    blocked: bool
    mode: RecallMode = "deterministic"
    semantic_note: str | None = None
    similarity: Mapping[str, float] | None = None


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class FactInput(Document):
    expected_version: int = Field(ge=0)
    source_revision: Identifier
    title: Text
    text: Text
    quote: Quote
    status: Literal["pending", "confirmed", "rejected"] = "pending"


class Fact(Document):
    id: Identifier
    revision_id: Identifier
    kind: Literal["fact"] = "fact"
    project_id: Identifier
    chapter_id: Identifier
    version: int = Field(ge=1)
    source_revision: Identifier
    title: Text
    text: Text
    quote: Quote
    status: Literal["pending", "confirmed", "rejected"]
    updated_at: str
    stale: bool = False


class SuggestedFact(Document):
    title: Text
    text: Text
    quote: Quote


class Finding(Document):
    quote: Quote
    explanation: Text
    instruction: Text
    fact_ids: list[Identifier] = Field(max_length=12)


class ReviewResult(Document):
    summary: Text
    facts: list[SuggestedFact] = Field(max_length=12)
    findings: list[Finding] = Field(max_length=12)


class PrepareReview(Document):
    source_revision: Identifier
    profile_id: Identifier


class SendReview(Document):
    expected_version: int = Field(ge=1)
    cloud_consent: bool = False


class FrozenFact(Document):
    id: Identifier
    revision_id: Identifier
    chapter_id: Identifier
    source_revision: Identifier
    title: Text
    text: Text
    quote: Quote


RECALL_ITEM_LIMIT = 24
RECALL_CHARACTER_LIMIT = 10_000
RECALL_EXPLANATION_LIMIT = 100


class ReviewRecallChoice(Document):
    """One fact frozen into a review and why it was chosen."""

    id: Identifier
    revision_id: Identifier
    chapter_id: Identifier
    title: str = Field(max_length=1000)
    reason: Literal["pinned", "related"]
    characters: int = Field(ge=0)
    # C-4: cosine similarity when the review was ranked semantically.
    similarity: float | None = Field(default=None, ge=-1, le=1)


class ReviewRecallOmission(Document):
    """A recallable fact left out of a prepared review (never an invalid pin: those refuse)."""

    id: Identifier
    title: str | None = Field(default=None, max_length=1000)
    reason: Literal["excluded", "budget"]


class ReviewRecall(Document):
    """Frozen explanation of the per-chapter recall policy applied when the review was prepared."""

    policy_version: int = Field(ge=0)
    pinned_fact_ids: list[Identifier] = Field(max_length=RECALL_ITEM_LIMIT)
    excluded_fact_ids: list[Identifier] = Field(max_length=200)
    selected: list[ReviewRecallChoice] = Field(max_length=RECALL_ITEM_LIMIT)
    omitted: list[ReviewRecallOmission] = Field(max_length=RECALL_EXPLANATION_LIMIT)
    omitted_total: int = Field(ge=0)
    excluded_total: int = Field(ge=0)
    used_characters: int = Field(ge=0)
    character_limit: int = RECALL_CHARACTER_LIMIT
    item_limit: int = RECALL_ITEM_LIMIT
    # C-4: how related facts were ordered. Reviews prepared earlier are deterministic.
    mode: RecallMode = "deterministic"
    semantic_note: str | None = Field(default=None, max_length=200)


class Review(Document):
    id: Identifier
    revision_id: Identifier
    kind: Literal["review"] = "review"
    project_id: Identifier
    chapter_id: Identifier
    version: int = Field(ge=1)
    source_revision: Identifier
    content: str = Field(min_length=1, max_length=24_000)
    content_truncated: bool
    model: dict[str, str | int]
    facts: list[FrozenFact] = Field(max_length=24)
    omitted_facts: int = Field(ge=0)
    # Reviews prepared before the recall policy applied to reviews carry no explanation.
    recall: ReviewRecall | None = None
    status: Literal["ready", "running", "completed", "failed"]
    attempts: int = Field(ge=0, le=3)
    result: ReviewResult | None
    last_error: str | None
    updated_at: str
    stale: bool = False


class Impact(Document):
    chapter_id: str
    title: str
    reason: str


class Workspace(Document):
    project_id: str
    chapter_id: str
    source_revision: str
    facts: list[Fact]
    reviews: list[Review]
    recalled_facts: list[FrozenFact]
    omitted_facts: int
    impacts: list[Impact]


MemoryItem = Fact | Review


class MemoryRepository(Protocol):
    def list(self, project_id: str) -> tuple[MemoryItem, ...]: ...

    def save(
        self, item: MemoryItem, expected_version: int, validate: Callable[[], None]
    ) -> MemoryItem: ...


def snapshot_model(model: ModelSnapshot) -> dict[str, str | int]:
    return {
        "id": model.id,
        "name": model.name,
        "kind": model.kind,
        "base_url": model.base_url,
        "model": model.model,
        "max_output_tokens": model.max_output_tokens,
    }
