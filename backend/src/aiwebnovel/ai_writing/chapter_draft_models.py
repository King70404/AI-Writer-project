"""F05 extension "章节候选稿" (``chapter_draft``) contracts.

A chapter draft is an independent candidate type, separate from the per-run continue
workflow. Preparing freezes, for one chapter, the saved revision it continues, the same
labelled writing context the continue workflow uses, the model snapshot and the author's
quota (at most ``MAX_SEGMENTS`` requests and ``MAX_DRAFT_CHARACTERS`` generated characters);
preparing never calls a model. Each segment is one explicit, metered request under the
``chapter_draft`` usage operation and must hold 200 to 300 non-whitespace characters (the
existing segment contract is not relaxed). Earlier segments of the same draft are sent to the
next request only as "本次候选稿" context: they never become facts, are never recalled by
another task and never change chapter text until the author adopts them.

Adoption appends the selected segments (or the whole draft) to the chapter in one write
transaction with an idempotency receipt, and only while the chapter is still at the revision
the draft tracks. A hand edit since then refuses adoption (409) and keeps the draft for
comparison; nothing is ever overwritten.

Before adoption the author may edit a pending segment (the model's original text is kept beside
the edit, and the edit is what later "本次候选稿" context and adoption use), discard a pending
segment (it is never sent again or adopted, and stays visible as discarded) or restore a
discarded segment. These changes never call a model, never return quota already used and never
touch chapter text.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.domain.errors import DomainError

MAX_SEGMENTS = 10
MAX_DRAFT_CHARACTERS = 3000
SEGMENT_MIN_CHARACTERS = 200
SEGMENT_MAX_CHARACTERS = 300
MAX_DRAFTS_PER_CHAPTER = 50
EVIDENCE_LIMIT = 2000
MAX_INSTRUCTION_CHARACTERS = 4000
MAX_SEGMENT_EDIT_CHARACTERS = 3000

DraftStatus = Literal["ready", "running", "failed", "exhausted"]
SegmentStatus = Literal["pending", "adopted", "discarded"]
SegmentAction = Literal["edit", "discard", "restore"]


class ChapterDraftConflict(DomainError):
    message = "The chapter draft is not in a state that allows this action. Reload it."


class ChapterDraftStale(DomainError):
    message = (
        "The chapter text changed since the draft's baseline revision; "
        "the draft was kept for comparison and nothing was written."
    )


class ChapterDraftInvalid(DomainError):
    message = "The chapter draft request is invalid."


class ChapterDraftNotFound(DomainError):
    message = "The chapter draft is unavailable."


class ChapterDraftConsentRequired(DomainError):
    message = "Confirm sending the chapter context to the cloud model."


class ChapterDraftQuotaExhausted(DomainError):
    message = "The chapter draft has no request or character quota left."


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class DraftSegment(Strict):
    index: int = Field(ge=0)
    attempt: int = Field(ge=1)
    text: str
    characters: int
    model: str
    status: SegmentStatus = "pending"
    adopted_revision_id: str | None = None
    # The author's edit of a pending segment; ``text`` stays the model's original reply.
    edited_text: str | None = None
    edited_characters: int | None = None
    edited_at: str | None = None
    discarded_at: str | None = None


def segment_text(segment: DraftSegment) -> str:
    """The text the author currently stands behind: the edit when there is one."""
    return segment.text if segment.edited_text is None else segment.edited_text


def segment_characters(segment: DraftSegment) -> int:
    return segment.characters if segment.edited_characters is None else segment.edited_characters


class DraftFailure(Strict):
    attempt: int = Field(ge=1)
    error: str
    # The rejected reply (wrong length) is kept as evidence; provider errors keep no text.
    evidence: str | None = None
    evidence_truncated: bool = False
    at: str


class DraftReceipt(Strict):
    idempotency_key: str
    segment_indexes: list[int]
    revision_id: str
    version: int
    adopted_at: str


class FrozenContext(Strict):
    text: str
    sha256: str
    included_sources: list[str]
    omitted_sources: list[str]
    truncated: bool
    character_count: int


class ChapterDraft(Strict):
    id: str
    project_id: str
    chapter_id: str
    status: DraftStatus
    model: dict[str, str | int]
    instruction: str
    max_segments: int = Field(ge=1, le=MAX_SEGMENTS)
    max_output_characters: int = Field(ge=SEGMENT_MIN_CHARACTERS, le=MAX_DRAFT_CHARACTERS)
    attempts: int = Field(ge=0)
    generated_characters: int = Field(ge=0)
    # The saved chapter revision the draft was prepared against.
    base_revision_id: str
    base_version: int
    # The revision the draft continues now: advances only through the draft's own adoption.
    current_revision_id: str
    current_version: int
    context: FrozenContext
    segments: list[DraftSegment] = []
    failures: list[DraftFailure] = []
    receipts: list[DraftReceipt] = []
    last_error: str | None = None
    writing_job_id: str | None = None
    created_at: str
    updated_at: str


class ChapterDraftView(Strict):
    id: str
    project_id: str
    chapter_id: str
    version: int
    status: DraftStatus
    model: dict[str, str | int]
    instruction: str
    max_segments: int
    max_output_characters: int
    attempts: int
    generated_characters: int
    remaining_requests: int
    remaining_characters: int
    can_send: bool
    base_revision_id: str
    current_revision_id: str
    current_version: int
    included_sources: list[str]
    omitted_sources: list[str]
    context_truncated: bool
    segments: list[DraftSegment]
    failures: list[DraftFailure]
    receipts: list[DraftReceipt]
    last_error: str | None
    writing_job_id: str | None
    created_at: str
    updated_at: str
    # The exact messages the next segment request would transmit, for the author's preview.
    next_request_preview: str


class ChapterDraftSummary(Strict):
    id: str
    version: int
    status: DraftStatus
    segments: int
    adopted: int
    discarded: int
    edited: int
    generated_characters: int
    writing_job_id: str | None
    created_at: str


class ChapterDraftList(Strict):
    chapter_id: str
    items: list[ChapterDraftSummary]


class PrepareChapterDraft(Strict):
    profile_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    instruction: str = Field(default="", max_length=MAX_INSTRUCTION_CHARACTERS)
    max_segments: int = Field(default=MAX_SEGMENTS, ge=1, le=MAX_SEGMENTS)
    max_output_characters: int = Field(
        default=MAX_DRAFT_CHARACTERS, ge=SEGMENT_MIN_CHARACTERS, le=MAX_DRAFT_CHARACTERS
    )
    # Optional D3 writing job whose current step is this chapter; its quota is then shared.
    writing_job_id: str | None = Field(default=None, min_length=36, max_length=36)


class SendChapterDraft(Strict):
    expected_version: int = Field(ge=1)
    cloud_consent: bool = False
    # How many segments the author confirms for this send; stops earlier on any failure.
    segments: int = Field(default=1, ge=1, le=MAX_SEGMENTS)


class AdoptChapterDraft(Strict):
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    # Ascending pending segment indexes; omitted means the whole remaining draft.
    segment_indexes: list[int] | None = Field(default=None, min_length=1, max_length=MAX_SEGMENTS)


class ChangeDraftSegment(Strict):
    """Edit, discard or restore one segment; never calls a model or writes chapter text."""

    expected_version: int = Field(ge=1)
    action: SegmentAction
    # Required for ``edit`` only; the original text again removes the edit.
    text: str | None = Field(default=None, min_length=1, max_length=MAX_SEGMENT_EDIT_CHARACTERS)
