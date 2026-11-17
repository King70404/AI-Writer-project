"""Bounded workbench read contracts; every number is derived from persisted data.

Character counts are the number of non-whitespace Unicode characters (Python
``str.isspace``) of each chapter's current saved manuscript revision. AI candidates,
plans and memory never contribute to these totals.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aiwebnovel.domain.errors import DomainError

EditorialStatus = Literal["draft", "review", "final"]
ActionKind = Literal[
    "pending_candidate",
    "stale_fact",
    "pending_fact",
    "stale_review",
    "unfinished_review",
    "final_changed",
    "due_thread",
    "budget_reminder",
]
# Fixed presentation order: problems that make AI context unreliable come first.
ACTION_ORDER: tuple[ActionKind, ...] = (
    "stale_fact",
    "stale_review",
    "final_changed",
    "pending_candidate",
    "pending_fact",
    "unfinished_review",
    "due_thread",
    "budget_reminder",
)
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


class EditorialConflict(DomainError):
    message = "The chapter editorial state changed. Reload it before saving."


class WorkbenchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SaveEditorialState(WorkbenchModel):
    status: EditorialStatus
    expected_version: int = Field(ge=0)


class EditorialState(WorkbenchModel):
    chapter_id: str
    project_id: str
    status: EditorialStatus
    # Zero means the author has not chosen a state; ``draft`` is then implied.
    version: int = Field(ge=0)
    chapter_revision_id: str | None
    content_changed: bool
    # Derived open to-dos for this chapter, excluding the "changed after final" note.
    open_actions: int = Field(default=0, ge=0)
    updated_at: str | None


class EditorialCounts(WorkbenchModel):
    draft: int = Field(ge=0)
    review: int = Field(ge=0)
    final: int = Field(ge=0)


class LatestChapter(WorkbenchModel):
    chapter_id: str
    volume_id: str
    title: str
    position: int
    updated_at: str


class VolumeSummary(WorkbenchModel):
    volume_id: str
    title: str
    position: int
    chapter_count: int = Field(ge=0)
    characters: int = Field(ge=0)
    editorial: EditorialCounts


class ActionCount(WorkbenchModel):
    kind: ActionKind
    items: int = Field(ge=0)
    chapters: int = Field(ge=0)


class WorkspaceSummary(WorkbenchModel):
    project_id: str
    characters: int = Field(ge=0)
    chapter_count: int = Field(ge=0)
    volume_count: int = Field(ge=0)
    editorial: EditorialCounts
    latest_chapter: LatestChapter | None
    volumes: list[VolumeSummary]
    actions: list[ActionCount]
    action_total: int = Field(ge=0)
    generated_at: str


class BookshelfSummary(WorkbenchModel):
    project_id: str
    title: str
    characters: int = Field(ge=0)
    chapter_count: int = Field(ge=0)
    volume_count: int = Field(ge=0)
    editorial: EditorialCounts
    action_total: int = Field(ge=0)


class BookshelfPage(WorkbenchModel):
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=MAX_PAGE_SIZE)
    next_offset: int | None
    items: list[BookshelfSummary]
    generated_at: str


class ChapterSummary(WorkbenchModel):
    chapter_id: str
    volume_id: str
    title: str
    position: int
    characters: int = Field(ge=0)
    updated_at: str
    editorial_status: EditorialStatus
    editorial_version: int = Field(ge=0)
    content_changed_since_editorial: bool
    open_actions: int = Field(ge=0)


class ChapterSummaryPage(WorkbenchModel):
    project_id: str
    volume_id: str | None
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=MAX_PAGE_SIZE)
    next_offset: int | None
    items: list[ChapterSummary]


class ActionItem(WorkbenchModel):
    kind: ActionKind
    chapter_id: str | None
    volume_id: str | None
    chapter_title: str
    chapter_position: int
    volume_position: int
    count: int = Field(ge=1)
    entity_id: str | None = None
    target_kind: Literal["chapter", "thread", "budget"] = "chapter"


class ActionPage(WorkbenchModel):
    project_id: str
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=MAX_PAGE_SIZE)
    next_offset: int | None
    items: list[ActionItem]
