"""Author-owned long-form story control contracts (plans, plot threads, timeline, recall).

Everything here is entered or changed by the author. Plans and plot threads are writing
guidance, never confirmed story facts; recall policies only choose among facts the author
already confirmed. No contract in this module causes a model request.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.story_memory.models import RecallPinsInvalid as RecallPinsInvalid

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,60}$")]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Note = Annotated[str, StringConstraints(max_length=2000)]
Quote = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]

MAX_GOALS = 500
MAX_THREADS = 1000
MAX_EVENTS = 2000
MAX_STATES = 2000
MAX_PINNED = 24
MAX_EXCLUDED = 200
RECALL_ITEM_LIMIT = 24
RECALL_CHARACTER_LIMIT = 10_000

GoalScope = Literal["book", "volume"]
GoalStatus = Literal["active", "archived"]
LinkStatus = Literal["planned", "reflected", "deferred", "abandoned"]
ThreadStatus = Literal["planned", "planted", "advancing", "paid_off", "abandoned"]
ThreadPriority = Literal["high", "normal", "low"]
AnchorRole = Literal["setup", "advance", "payoff"]
StateAttribute = Literal["identity", "injury", "possession", "knowledge", "other"]
ControlKind = Literal["goal", "thread", "event", "state", "recall_policy"]


class StoryControlConflict(DomainError):
    message = "The story plan changed. Reload it before saving."


class StoryControlInvalid(DomainError):
    message = "The story plan input or one of its references is invalid."


class StoryControlNotFound(DomainError):
    message = "The story plan item is unavailable."


class StoryControlCycle(DomainError):
    message = "The goal or event relations would form a cycle."


class ControlModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    def _texts(self) -> list[str]:
        return []

    @model_validator(mode="after")
    def safe_text(self) -> Self:
        # Reject controls and unpaired surrogates that cannot safely cross a model boundary.
        for text in self._texts():
            if any((ord(c) < 32 and c not in "\n\r\t") or 0xD800 <= ord(c) <= 0xDFFF for c in text):
                raise ValueError("Text contains unsupported control characters.")
        return self


def _unique(values: list[str]) -> bool:
    return len(values) == len(set(values))


class GoalLink(ControlModel):
    chapter_id: Identifier
    status: LinkStatus = "planned"
    chapter_revision_id: Identifier | None = None
    quote: Quote | None = None
    note: Note = ""

    def _texts(self) -> list[str]:
        return [self.note, self.quote or ""]

    @model_validator(mode="after")
    def evidence_pair(self) -> Self:
        if (self.quote is None) != (self.chapter_revision_id is None):
            raise ValueError("Evidence needs both a quote and its chapter revision.")
        return self


class GoalDocument(ControlModel):
    scope: GoalScope
    volume_id: Identifier | None = None
    parent_goal_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    title: Title
    conflict: Note = ""
    desire: Note = ""
    obstacle: Note = ""
    turn: Note = ""
    outcome: Note = ""
    opening_state: Note = ""
    target_characters: int | None = Field(default=None, ge=1, le=10_000_000)
    status: GoalStatus = "active"
    links: list[GoalLink] = Field(default_factory=list, max_length=100)

    def _texts(self) -> list[str]:
        return [
            self.title,
            self.conflict,
            self.desire,
            self.obstacle,
            self.turn,
            self.outcome,
            self.opening_state,
        ]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.scope == "volume") != (self.volume_id is not None):
            raise ValueError("Only a volume goal names a volume.")
        if not _unique(self.parent_goal_ids) or not _unique([i.chapter_id for i in self.links]):
            raise ValueError("Parent goals and linked chapters must not repeat.")
        return self


class SaveGoal(GoalDocument):
    expected_version: int = Field(ge=0)


class EvidenceAnchor(ControlModel):
    role: AnchorRole
    chapter_id: Identifier
    chapter_revision_id: Identifier
    quote: Quote

    def _texts(self) -> list[str]:
        return [self.quote]


class ThreadDocument(ControlModel):
    title: Title
    content: Note = ""
    character_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    planned_setup_chapter_id: Identifier | None = None
    planned_payoff_chapter_id: Identifier | None = None
    planned_payoff_volume_id: Identifier | None = None
    priority: ThreadPriority = "normal"
    status: ThreadStatus = "planned"
    note: Note = ""
    anchors: list[EvidenceAnchor] = Field(default_factory=list, max_length=30)

    def _texts(self) -> list[str]:
        return [self.title, self.content, self.note]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if not _unique(self.character_ids):
            raise ValueError("Characters must not repeat.")
        if self.planned_payoff_chapter_id is not None and self.planned_payoff_volume_id is not None:
            raise ValueError("Plan the payoff in one chapter or one volume.")
        roles = {anchor.role for anchor in self.anchors}
        if self.status in ("planted", "advancing") and "setup" not in roles:
            raise ValueError("A planted thread needs setup evidence.")
        if self.status == "paid_off" and "payoff" not in roles:
            raise ValueError("A paid-off thread needs payoff evidence.")
        if self.status == "abandoned" and not self.note.strip():
            raise ValueError("Record why the thread was abandoned.")
        return self


class SaveThread(ThreadDocument):
    expected_version: int = Field(ge=0)


class EventDocument(ControlModel):
    title: Title
    description: Note = ""
    story_time: Annotated[str, StringConstraints(max_length=120)] = ""
    chapter_id: Identifier | None = None
    character_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    after_event_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    before_event_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    archived: bool = False

    def _texts(self) -> list[str]:
        return [self.title, self.description, self.story_time]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if not (
            _unique(self.character_ids)
            and _unique(self.after_event_ids)
            and _unique(self.before_event_ids)
        ) or set(self.after_event_ids) & set(self.before_event_ids):
            raise ValueError("Relations must not repeat or contradict each other.")
        return self


class SaveEvent(EventDocument):
    expected_version: int = Field(ge=0)


class StateDocument(ControlModel):
    character_id: Identifier
    attribute: StateAttribute
    label: Title
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    start_event_id: Identifier
    end_event_id: Identifier | None = None
    fact_ids: list[Identifier] = Field(default_factory=list, max_length=12)
    archived: bool = False

    def _texts(self) -> list[str]:
        return [self.label, self.value]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.end_event_id == self.start_event_id or not _unique(self.fact_ids):
            raise ValueError("A state interval needs distinct start and end events.")
        return self


class SaveState(StateDocument):
    expected_version: int = Field(ge=0)


class RecallPolicyDocument(ControlModel):
    pinned_fact_ids: list[Identifier] = Field(default_factory=list, max_length=MAX_PINNED)
    excluded_fact_ids: list[Identifier] = Field(default_factory=list, max_length=MAX_EXCLUDED)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            not _unique(self.pinned_fact_ids)
            or not _unique(self.excluded_fact_ids)
            or set(self.pinned_fact_ids) & set(self.excluded_fact_ids)
        ):
            raise ValueError("A fact is either pinned or excluded, once.")
        return self


class SaveRecallPolicy(RecallPolicyDocument):
    expected_version: int = Field(ge=0)


class Stored(ControlModel):
    id: Identifier
    revision_id: Identifier
    project_id: Identifier
    version: int = Field(ge=1)
    created_at: str
    updated_at: str


class Goal(Stored, GoalDocument):
    kind: Literal["goal"] = "goal"


class Thread(Stored, ThreadDocument):
    kind: Literal["thread"] = "thread"


class Event(Stored, EventDocument):
    kind: Literal["event"] = "event"


class State(Stored, StateDocument):
    kind: Literal["state"] = "state"


class RecallPolicy(Stored, RecallPolicyDocument):
    kind: Literal["recall_policy"] = "recall_policy"
    chapter_id: Identifier


ControlItem = Goal | Thread | Event | State | RecallPolicy

# ---------------------------------------------------------------------------
# Read models.


class LinkView(ControlModel):
    chapter_id: str
    chapter_title: str | None
    status: LinkStatus
    note: str
    quote: str | None
    chapter_revision_id: str | None
    # missing: the chapter left this project; evidence_stale: the quoted text changed.
    problem: Literal["missing", "evidence_stale"] | None


class GoalView(ControlModel):
    goal: Goal
    links: list[LinkView]
    child_goal_ids: list[str]
    reflected: int
    open_links: int


class VolumeOption(ControlModel):
    volume_id: str
    title: str
    position: int


class ChapterOption(ControlModel):
    chapter_id: str
    volume_id: str
    title: str
    volume_position: int
    position: int
    revision_id: str


class CharacterOption(ControlModel):
    character_id: str
    name: str


class ArcPlan(ControlModel):
    project_id: str
    goals: list[GoalView]
    # Choices for the author's forms; titles only, never manuscript text.
    volumes: list[VolumeOption]
    chapters: list[ChapterOption]
    characters: list[CharacterOption]


class AnchorView(ControlModel):
    anchor: EvidenceAnchor
    chapter_title: str | None
    stale: bool


class ThreadView(ControlModel):
    thread: Thread
    anchors: list[AnchorView]
    evidence_stale: bool
    due: bool
    due_reason: str | None


class EventView(ControlModel):
    event: Event
    story_order: int
    narrative_position: list[int] | None
    chapter_title: str | None


class StateView(ControlModel):
    state: State
    invalid_fact_ids: list[str]


class TimelineWarning(ControlModel):
    kind: Literal["state_overlap", "state_order_unknown"]
    state_ids: list[str]
    message: str


class Timeline(ControlModel):
    project_id: str
    threads: list[ThreadView]
    events: list[EventView]
    states: list[StateView]
    warnings: list[TimelineWarning]


class ChapterGuide(ControlModel):
    chapter_id: str
    project_id: str
    goals: list[GoalView]
    setup_threads: list[ThreadView]
    payoff_threads: list[ThreadView]
    due_threads: list[ThreadView]


class FactHit(ControlModel):
    id: str
    revision_id: str
    chapter_id: str
    chapter_title: str | None
    title: str
    text: str
    quote: str
    status: Literal["pending", "confirmed", "rejected"]
    stale: bool
    recallable_here: bool | None


class FactSearchPage(ControlModel):
    items: list[FactHit]
    total: int
    offset: int
    limit: int


RecallReason = Literal["pinned", "related"]
OmitReason = Literal[
    "excluded",
    "budget",
    "pin_not_confirmed",
    "pin_stale",
    "pin_not_earlier",
    "pin_missing",
    "pin_over_budget",
]


class RecallChoice(ControlModel):
    id: str
    revision_id: str
    chapter_id: str
    title: str
    reason: RecallReason
    characters: int


class RecallOmission(ControlModel):
    id: str
    title: str | None
    reason: OmitReason


class RecallPreview(ControlModel):
    chapter_id: str
    policy_version: int
    selected: list[RecallChoice]
    omitted: list[RecallOmission]
    omitted_total: int
    excluded_total: int
    used_characters: int
    character_limit: int
    item_limit: int
    # True when a pinned fact is invalid or over budget: preparing a task is refused.
    blocked: bool


class RecallPreviewInput(RecallPolicyDocument):
    pass


class RecallPolicyState(ControlModel):
    chapter_id: str
    version: int
    pinned_fact_ids: list[str]
    excluded_fact_ids: list[str]
    updated_at: str | None
