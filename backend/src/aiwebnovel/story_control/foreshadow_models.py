"""Batch foreshadow extraction (F03 "批量提取伏笔建议") contracts.

The author picks a bounded range of chapters (at most ``MAX_CHAPTERS`` with at most
``MAX_TOTAL_CHARACTERS`` of saved text). Preparing freezes each chapter's saved revision and
text plus the open plot threads and their versions; preparing never calls a model. The
frozen snapshot is sent once, on an explicit author action, as a single metered request.
The reply is parsed as strict JSON into suggestion cards: a new plot thread planted in a
frozen chapter, or the payoff of a frozen open thread. Every card's quote is checked
verbatim against the frozen chapter text; a card whose quote is not found (or that names a
chapter or thread outside the snapshot) is kept but marked invalid and cannot be adopted.
Only the author's adoption of selected valid cards writes plot threads, through the normal
story control validation, and only while the quoted chapter revision and the thread are
still exactly as frozen.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.story_control.models import Identifier

MAX_CHAPTERS = 10
MAX_TOTAL_CHARACTERS = 30_000
MAX_FROZEN_THREADS = 100
FROZEN_THREAD_TEXT_LIMIT = 300
MAX_CARDS = 30
MAX_QUOTE_CHARACTERS = 300
MAX_PROPOSALS_PER_PROJECT = 200
MAX_OUTPUT_CHARACTERS = 60_000
EVIDENCE_LIMIT = 20_000
FORESHADOW_OUTPUT_LIMIT = 16_000

CardTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
CardText = Annotated[str, StringConstraints(max_length=1000)]
CardQuote = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUOTE_CHARACTERS)
]
Reason = Annotated[str, StringConstraints(max_length=500)]
ExtractionStatus = Literal["ready", "running", "completed", "failed"]
RangeProblem = Literal["too_many_chapters", "too_many_characters", "empty_chapter"]
AdoptAction = Literal["created", "paid_off", "already_recorded"]
CardProblem = Literal[
    "quote_not_found", "unknown_chapter", "unknown_thread", "duplicate_payoff", "duplicate_title"
]


class ForeshadowConflict(DomainError):
    message = "The foreshadow suggestion is not in a state that allows this action. Reload it."


class ForeshadowStale(DomainError):
    message = "The chapter text or plot thread changed after preparation. Prepare it again."


class ForeshadowInvalid(DomainError):
    message = "The foreshadow extraction request is invalid."


class ForeshadowNotFound(DomainError):
    message = "The foreshadow suggestion is unavailable."


class ForeshadowConsentRequired(DomainError):
    message = "Confirm sending the frozen chapter text to the cloud model."


class ForeshadowOutputInvalid(DomainError):
    message = "The model reply was not valid suggestion JSON; it was kept as evidence."


class ForeshadowCardInvalid(DomainError):
    message = "The selected card's evidence was not found in the frozen chapter text."


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _safe(texts: list[str]) -> None:
    for text in texts:
        if any((ord(c) < 32 and c not in "\n\r\t") or 0xD800 <= ord(c) <= 0xDFFF for c in text):
            raise ValueError("Text contains unsupported control characters.")


# ---------------------------------------------------------------------------- model output


class NewThreadCard(Strict):
    kind: Literal["new_thread"]
    title: CardTitle
    content: CardText = ""
    chapter_id: Identifier
    quote: CardQuote
    reason: Reason = ""

    @model_validator(mode="after")
    def checked(self) -> Self:
        _safe([self.title, self.content, self.quote, self.reason])
        return self


class PayoffCard(Strict):
    kind: Literal["payoff"]
    thread_id: Identifier
    chapter_id: Identifier
    quote: CardQuote
    reason: Reason = ""

    @model_validator(mode="after")
    def checked(self) -> Self:
        _safe([self.quote, self.reason])
        return self


Card = Annotated[NewThreadCard | PayoffCard, Field(discriminator="kind")]


class ExtractionOutput(Strict):
    summary: CardText = ""
    cards: list[Card] = Field(max_length=MAX_CARDS)

    @model_validator(mode="after")
    def checked(self) -> Self:
        _safe([self.summary])
        return self


class CardCheck(Strict):
    """Server verdict for one card; only a valid card can be adopted."""

    valid: bool
    problem: CardProblem | None = None


# ---------------------------------------------------------------------------- frozen snapshot


class FrozenChapterText(Strict):
    chapter_id: str
    volume_id: str
    title: str
    volume_position: int
    position: int
    revision_id: str
    characters: int = Field(ge=0)
    content: str


class FrozenThread(Strict):
    id: str
    version: int
    title: str
    content: str
    status: Literal["planned", "planted", "advancing"]
    setup_chapter_ids: list[str]


class Adoption(Strict):
    index: int
    action: AdoptAction
    thread_id: str
    thread_version: int
    adopted_at: str


class ForeshadowProposal(Strict):
    id: str
    project_id: str
    status: ExtractionStatus
    attempts: int = Field(ge=0, le=1)
    model: dict[str, str | int]
    author_request: str
    chapters: list[FrozenChapterText] = Field(min_length=1, max_length=MAX_CHAPTERS)
    total_characters: int = Field(ge=1, le=MAX_TOTAL_CHARACTERS)
    threads: list[FrozenThread]
    threads_omitted: int = Field(ge=0)
    summary: str | None = None
    cards: list[Card] = Field(default_factory=list, max_length=MAX_CARDS)
    checks: list[CardCheck] = Field(default_factory=list, max_length=MAX_CARDS)
    error: str | None = None
    evidence: str | None = None
    evidence_truncated: bool = False
    adoptions: list[Adoption] = Field(default_factory=list, max_length=MAX_CARDS)
    # Thread versions this proposal expects; its own payoff adoptions move them forward.
    thread_versions: dict[str, int]
    created_thread_ids: list[str] = Field(default_factory=list, max_length=MAX_CARDS)
    created_at: str
    updated_at: str


class ChapterRef(Strict):
    """A frozen chapter as shown to the author: no text, only its size and revision."""

    chapter_id: str
    volume_id: str
    title: str
    volume_position: int
    position: int
    revision_id: str
    characters: int


class ForeshadowProposalView(Strict):
    id: str
    project_id: str
    version: int
    status: ExtractionStatus
    attempts: int
    model: dict[str, str | int]
    author_request: str
    chapters: list[ChapterRef]
    total_characters: int
    threads: list[FrozenThread]
    threads_omitted: int
    summary: str | None
    cards: list[Card]
    checks: list[CardCheck]
    error: str | None
    evidence: str | None
    evidence_truncated: bool
    adoptions: list[Adoption]
    created_at: str
    updated_at: str
    # The exact system and user messages one send transmits, for the author's preview.
    request_preview: str


class ForeshadowProposalSummary(Strict):
    id: str
    version: int
    status: ExtractionStatus
    chapter_ids: list[str]
    total_characters: int
    cards: int
    adopted: int
    created_at: str


class ForeshadowProposalList(Strict):
    project_id: str
    items: list[ForeshadowProposalSummary]


class RangePreviewChapter(Strict):
    chapter_id: str
    title: str
    volume_position: int
    position: int
    characters: int


class RangePreview(Strict):
    """What preparing would freeze; computed locally with zero model requests."""

    chapters: list[RangePreviewChapter]
    total_characters: int
    max_chapters: int
    max_total_characters: int
    open_threads: int
    threads_omitted: int
    problem: RangeProblem | None


# ---------------------------------------------------------------------------- HTTP input


def _distinct(ids: list[str]) -> None:
    if len(set(ids)) != len(ids):
        raise ValueError("Chapters must not repeat.")


class PreviewRange(Strict):
    chapter_ids: list[Identifier] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def checked(self) -> Self:
        _distinct(self.chapter_ids)
        return self


class PrepareExtraction(Strict):
    chapter_ids: list[Identifier] = Field(min_length=1, max_length=MAX_CHAPTERS)
    profile_id: str = Field(min_length=1, max_length=100)
    author_request: Annotated[str, StringConstraints(max_length=500)] = ""

    @model_validator(mode="after")
    def checked(self) -> Self:
        _distinct(self.chapter_ids)
        _safe([self.author_request])
        return self


class SendExtraction(Strict):
    expected_version: int = Field(ge=1)
    cloud_consent: bool = False


class AdoptForeshadowCards(Strict):
    card_indexes: list[int] = Field(min_length=1, max_length=MAX_CARDS)

    @model_validator(mode="after")
    def checked(self) -> Self:
        if len(set(self.card_indexes)) != len(self.card_indexes) or any(
            not 0 <= index < MAX_CARDS for index in self.card_indexes
        ):
            raise ValueError("Card indexes must be distinct and in range.")
        return self
