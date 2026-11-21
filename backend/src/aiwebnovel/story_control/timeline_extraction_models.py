"""Batch story event and character state extraction (F03, beside C-2) contracts.

The author picks the same bounded range of chapters as the foreshadow extraction (at most
``MAX_CHAPTERS`` with at most ``MAX_TOTAL_CHARACTERS`` of saved text). Preparing freezes each
chapter's saved revision and text plus the project's characters, active story events and
open character states (with their versions); preparing never calls a model. The frozen
snapshot is sent once, on an explicit author action, as a single metered request. The reply
is parsed as strict JSON into evidence cards: a story event that happens in a frozen chapter,
or a character state that starts at a frozen event or at an event card of the same reply and
may end one frozen open state of the same character. Every card's quote is checked verbatim
against the frozen chapter text; a card whose quote is not found (or that names a chapter,
character, event or state outside the snapshot) is kept but marked invalid and cannot be
adopted. Only the author's adoption of selected valid cards writes events and state
intervals, through the normal story control validation, and only while the quoted chapter
revision and any ended state are still exactly as frozen.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.story_control.foreshadow_models import (
    MAX_CARDS,
    CardQuote,
    CardText,
    CardTitle,
    ChapterRef,
    FrozenChapterText,
    RangeProblem,
    Reason,
    Strict,
    _distinct,
    _safe,
)
from aiwebnovel.story_control.models import Identifier, StateAttribute

MAX_FROZEN_EVENTS = 100
MAX_FROZEN_STATES = 100
MAX_FROZEN_CHARACTERS = 200
FROZEN_TEXT_LIMIT = 300
TIMELINE_OUTPUT_LIMIT = 16_000

StoryTime = Annotated[str, StringConstraints(max_length=120)]
StateValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
ExtractionStatus = Literal["ready", "running", "completed", "failed"]
AdoptAction = Literal["event_created", "state_created"]
CardProblem = Literal[
    "quote_not_found",
    "unknown_chapter",
    "unknown_character",
    "unknown_event",
    "unknown_state",
    "unknown_event_card",
    "duplicate_title",
    "duplicate_end",
    "state_mismatch",
]


class TimelineConflict(DomainError):
    message = "The timeline suggestion is not in a state that allows this action. Reload it."


class TimelineStale(DomainError):
    message = "The chapter text, an event or a state changed after preparation. Prepare again."


class TimelineInvalid(DomainError):
    message = "The timeline extraction request is invalid."


class TimelineNotFound(DomainError):
    message = "The timeline suggestion is unavailable."


class TimelineConsentRequired(DomainError):
    message = "Confirm sending the frozen chapter text to the cloud model."


class TimelineOutputInvalid(DomainError):
    message = "The model reply was not valid suggestion JSON; it was kept as evidence."


class TimelineCardInvalid(DomainError):
    message = "The selected card's evidence was not found in the frozen chapter text."


class TimelineCardNeedsEvent(DomainError):
    message = "A selected state starts at a suggested event that is not adopted or selected."


# ---------------------------------------------------------------------------- model output


class EventCard(Strict):
    kind: Literal["event"]
    title: CardTitle
    description: CardText = ""
    story_time: StoryTime = ""
    chapter_id: Identifier
    character_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    after_event_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    quote: CardQuote
    reason: Reason = ""

    @model_validator(mode="after")
    def checked(self) -> Self:
        _safe([self.title, self.description, self.story_time, self.quote, self.reason])
        _distinct(self.character_ids)
        _distinct(self.after_event_ids)
        return self


class StateCard(Strict):
    kind: Literal["state"]
    character_id: Identifier
    attribute: StateAttribute
    label: CardTitle
    value: StateValue
    chapter_id: Identifier
    quote: CardQuote
    # Exactly one: an existing frozen event, or the index of an event card in this reply.
    start_event_id: Identifier | None = None
    start_event_card: int | None = Field(default=None, ge=0, lt=MAX_CARDS)
    # An open frozen state of the same character that this new state replaces.
    ends_state_id: Identifier | None = None
    reason: Reason = ""

    @model_validator(mode="after")
    def checked(self) -> Self:
        _safe([self.label, self.value, self.quote, self.reason])
        if (self.start_event_id is None) == (self.start_event_card is None):
            raise ValueError("A state starts at exactly one event or event card.")
        return self


Card = Annotated[EventCard | StateCard, Field(discriminator="kind")]


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


class FrozenCharacter(Strict):
    character_id: str
    name: str


class FrozenEvent(Strict):
    id: str
    version: int
    title: str
    description: str
    story_time: str
    chapter_id: str | None
    character_ids: list[str]


class FrozenState(Strict):
    id: str
    version: int
    character_id: str
    attribute: str
    label: str
    value: str
    start_event_id: str


class Adoption(Strict):
    index: int
    action: AdoptAction
    target_id: str
    ended_state_id: str | None = None
    adopted_at: str


class TimelineProposal(Strict):
    id: str
    project_id: str
    status: ExtractionStatus
    attempts: int = Field(ge=0, le=1)
    model: dict[str, str | int]
    author_request: str
    chapters: list[FrozenChapterText] = Field(min_length=1)
    total_characters: int = Field(ge=1)
    characters: list[FrozenCharacter]
    events: list[FrozenEvent]
    events_omitted: int = Field(ge=0)
    states: list[FrozenState]
    states_omitted: int = Field(ge=0)
    summary: str | None = None
    cards: list[Card] = Field(default_factory=list, max_length=MAX_CARDS)
    checks: list[CardCheck] = Field(default_factory=list, max_length=MAX_CARDS)
    error: str | None = None
    evidence: str | None = None
    evidence_truncated: bool = False
    adoptions: list[Adoption] = Field(default_factory=list, max_length=MAX_CARDS)
    # State versions this proposal expects; its own adoptions that end a state move them.
    state_versions: dict[str, int]
    created_at: str
    updated_at: str


class TimelineProposalView(Strict):
    id: str
    project_id: str
    version: int
    status: ExtractionStatus
    attempts: int
    model: dict[str, str | int]
    author_request: str
    chapters: list[ChapterRef]
    total_characters: int
    characters: list[FrozenCharacter]
    events: list[FrozenEvent]
    events_omitted: int
    states: list[FrozenState]
    states_omitted: int
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


class TimelineProposalSummary(Strict):
    id: str
    version: int
    status: ExtractionStatus
    chapter_ids: list[str]
    total_characters: int
    cards: int
    adopted: int
    created_at: str


class TimelineProposalList(Strict):
    project_id: str
    items: list[TimelineProposalSummary]


class TimelineRangeChapter(Strict):
    chapter_id: str
    title: str
    volume_position: int
    position: int
    characters: int


class TimelineRangePreview(Strict):
    """What preparing would freeze; computed locally with zero model requests."""

    chapters: list[TimelineRangeChapter]
    total_characters: int
    max_chapters: int
    max_total_characters: int
    characters: int
    events: int
    events_omitted: int
    open_states: int
    states_omitted: int
    problem: RangeProblem | None


# ---------------------------------------------------------------------------- HTTP input


class AdoptTimelineCards(Strict):
    card_indexes: list[int] = Field(min_length=1, max_length=MAX_CARDS)

    @model_validator(mode="after")
    def checked(self) -> Self:
        if len(set(self.card_indexes)) != len(self.card_indexes) or any(
            not 0 <= index < MAX_CARDS for index in self.card_indexes
        ):
            raise ValueError("Card indexes must be distinct and in range.")
        return self
