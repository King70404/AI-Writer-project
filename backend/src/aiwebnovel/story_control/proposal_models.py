"""Plan proposal (F02 "建议拆分") contracts: a frozen goal snapshot and model suggestion cards.

A proposal freezes the selected goal, its existing child goals, the version of every goal
in the novel and the volume/chapter titles at preparation; preparing never calls a model.
The model is sent the frozen snapshot once, on an explicit author action, and its reply is
parsed as strict JSON into bounded suggestion cards. Cards are suggestions only: a card
changes real plans only when the author adopts it, one card at a time, idempotently and
only while every goal still has the version frozen at preparation.

Before adopting, the author may edit a card's fields; the model's original card is kept
unchanged next to the edit for comparison, and adoption uses the edited card. An adopted
card can be undone: the goal it created is retracted, or the chapter link it added is
removed, but only while that plan is still exactly as this proposal left it; otherwise the
undo is refused so the author's later changes are never overwritten.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.story_control.models import Identifier

MAX_CARDS = 20
MAX_CARD_CHAPTERS = 20
MAX_FROZEN_CHAPTERS = 300
MAX_FROZEN_CHILDREN = 50
MAX_PROPOSALS_PER_PROJECT = 200
MAX_UNDOS = 100
MAX_OUTPUT_CHARACTERS = 40_000
EVIDENCE_LIMIT = 20_000
PROPOSAL_OUTPUT_LIMIT = 16_000

CardTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
CardText = Annotated[str, StringConstraints(max_length=1000)]
Reason = Annotated[str, StringConstraints(max_length=500)]
ProposalStatus = Literal["ready", "running", "completed", "failed"]
AdoptAction = Literal["created", "linked", "already_linked"]


class PlanProposalConflict(DomainError):
    message = "The suggestion is not in a state that allows this action. Reload it."


class PlanProposalStale(DomainError):
    message = "The story plan changed after the suggestion was prepared. Prepare it again."


class PlanProposalInvalid(DomainError):
    message = "The suggestion request is invalid."


class PlanProposalNotFound(DomainError):
    message = "The suggestion is unavailable."


class PlanProposalConsentRequired(DomainError):
    message = "Confirm sending the frozen plan snapshot to the cloud model."


class PlanProposalCardInvalid(DomainError):
    message = "The edited card is invalid or refers to a plan item outside the snapshot."


class PlanProposalUndoConflict(DomainError):
    message = (
        "The plan this card wrote was changed afterwards; undoing it would overwrite those "
        "changes. Reload the plan and change it by hand."
    )


class PlanProposalOutputInvalid(DomainError):
    message = "The model reply was not valid suggestion JSON; it was kept as evidence."


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _safe(texts: list[str]) -> None:
    for text in texts:
        if any((ord(c) < 32 and c not in "\n\r\t") or 0xD800 <= ord(c) <= 0xDFFF for c in text):
            raise ValueError("Text contains unsupported control characters.")


# ---------------------------------------------------------------------------- model output


class ChildGoalCard(Strict):
    kind: Literal["child_goal"]
    title: CardTitle
    volume_id: Identifier | None = None
    conflict: CardText = ""
    obstacle: CardText = ""
    turn: CardText = ""
    outcome: CardText = ""
    chapter_ids: list[Identifier] = Field(default_factory=list, max_length=MAX_CARD_CHAPTERS)
    reason: Reason = ""

    @model_validator(mode="after")
    def checked(self) -> Self:
        _safe([self.title, self.conflict, self.obstacle, self.turn, self.outcome, self.reason])
        if len(set(self.chapter_ids)) != len(self.chapter_ids):
            raise ValueError("Chapters must not repeat.")
        return self


class ChapterLinkCard(Strict):
    kind: Literal["chapter_link"]
    chapter_id: Identifier
    note: CardText = ""
    reason: Reason = ""

    @model_validator(mode="after")
    def checked(self) -> Self:
        _safe([self.note, self.reason])
        return self


Card = Annotated[ChildGoalCard | ChapterLinkCard, Field(discriminator="kind")]


class ProposalOutput(Strict):
    summary: CardText = ""
    cards: list[Card] = Field(max_length=MAX_CARDS)

    @model_validator(mode="after")
    def checked(self) -> Self:
        _safe([self.summary])
        linked = [card.chapter_id for card in self.cards if isinstance(card, ChapterLinkCard)]
        if len(set(linked)) != len(linked):
            raise ValueError("A chapter is suggested for the goal more than once.")
        return self


# ---------------------------------------------------------------------------- frozen snapshot


class FrozenGoal(Strict):
    id: str
    version: int
    scope: Literal["book", "volume"]
    volume_id: str | None
    title: str
    conflict: str
    desire: str
    obstacle: str
    turn: str
    outcome: str
    opening_state: str
    status: Literal["active", "archived"]
    linked_chapter_ids: list[str]


class FrozenVolume(Strict):
    volume_id: str
    title: str
    position: int


class FrozenChapter(Strict):
    chapter_id: str
    volume_id: str
    title: str
    volume_position: int
    position: int


class Adoption(Strict):
    index: int
    action: AdoptAction
    goal_id: str
    goal_version: int
    adopted_at: str
    # True when the author's edited card (not the model's original) was adopted.
    edited: bool = False


class CardEdit(Strict):
    """The author's edited version of one card; the original card stays in ``cards``."""

    index: int = Field(ge=0, lt=MAX_CARDS)
    card: Card
    edited_at: str


class Undo(Strict):
    index: int
    action: AdoptAction
    goal_id: str
    undone_at: str


class PlanProposal(Strict):
    id: str
    project_id: str
    goal_id: str
    status: ProposalStatus
    attempts: int = Field(ge=0, le=1)
    model: dict[str, str | int]
    author_request: str
    source: FrozenGoal
    children: list[FrozenGoal]
    goal_versions: dict[str, int]
    volumes: list[FrozenVolume]
    chapters: list[FrozenChapter]
    chapters_omitted: int = Field(ge=0)
    summary: str | None = None
    cards: list[Card] = Field(default_factory=list, max_length=MAX_CARDS)
    error: str | None = None
    evidence: str | None = None
    evidence_truncated: bool = False
    adoptions: list[Adoption] = Field(default_factory=list, max_length=MAX_CARDS)
    edits: list[CardEdit] = Field(default_factory=list, max_length=MAX_CARDS)
    undos: list[Undo] = Field(default_factory=list, max_length=MAX_UNDOS)
    known_goal_version: int
    created_goal_ids: list[str] = Field(default_factory=list, max_length=MAX_CARDS)
    created_at: str
    updated_at: str


class PlanProposalView(PlanProposal):
    version: int
    # The exact system and user messages one send transmits, for the author's preview.
    request_preview: str


# ---------------------------------------------------------------------------- HTTP input


class PrepareProposal(Strict):
    goal_id: Identifier
    profile_id: str = Field(min_length=1, max_length=100)
    author_request: Annotated[str, StringConstraints(max_length=500)] = ""

    @model_validator(mode="after")
    def checked(self) -> Self:
        _safe([self.author_request])
        return self


class SendProposal(Strict):
    expected_version: int = Field(ge=1)
    cloud_consent: bool = False


class AdoptCards(Strict):
    card_indexes: list[int] = Field(min_length=1, max_length=MAX_CARDS)

    @model_validator(mode="after")
    def checked(self) -> Self:
        if len(set(self.card_indexes)) != len(self.card_indexes) or any(
            not 0 <= index < MAX_CARDS for index in self.card_indexes
        ):
            raise ValueError("Card indexes must be distinct and in range.")
        return self


class EditCard(Strict):
    expected_version: int = Field(ge=1)
    # The edited card; null restores the model's original card.
    card: Card | None = None


class UndoAdoption(Strict):
    expected_version: int = Field(ge=1)
    card_index: int = Field(ge=0, lt=MAX_CARDS)


class PlanProposalList(Strict):
    project_id: str
    items: list[PlanProposalView]
