"""Plain snapshot rows shared by the workbench service and storage adapter.

Importing this module never registers ORM models or touches a database.
"""

from dataclasses import dataclass

from aiwebnovel.usage.budget import Spend
from aiwebnovel.workbench.models import EditorialStatus


@dataclass(frozen=True, slots=True)
class VolumeRow:
    volume_id: str
    title: str
    position: int


@dataclass(frozen=True, slots=True)
class ChapterRow:
    chapter_id: str
    volume_id: str
    volume_position: int
    position: int
    title: str
    revision_id: str
    updated_at: str
    characters: int


@dataclass(frozen=True, slots=True)
class EditorialRow:
    status: EditorialStatus
    version: int
    chapter_revision_id: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class FactReference:
    fact_id: str
    revision_id: str
    chapter_id: str


@dataclass(frozen=True, slots=True)
class MemoryRow:
    entity_id: str
    chapter_id: str
    kind: str
    status: str
    source_revision: str
    revision_id: str
    updated_at: str
    facts: tuple[FactReference, ...]


@dataclass(frozen=True, slots=True)
class ThreadReminderRow:
    entity_id: str
    title: str
    status: str
    payoff_chapter_id: str | None
    payoff_volume_id: str | None
    anchors: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class BudgetReminderRow:
    mode: str
    monthly_limit: int | None
    spend: Spend


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    volumes: tuple[VolumeRow, ...]
    chapters: tuple[ChapterRow, ...]
    editorial: dict[str, EditorialRow]
    pending_candidates: dict[str, int]
    memory: tuple[MemoryRow, ...]
    threads: tuple[ThreadReminderRow, ...] = ()
    budget: BudgetReminderRow | None = None
