"""Plain snapshot rows shared by the workbench service and storage adapter.

Importing this module never registers ORM models or touches a database.
"""

from dataclasses import dataclass

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
class ProjectSnapshot:
    volumes: tuple[VolumeRow, ...]
    chapters: tuple[ChapterRow, ...]
    editorial: dict[str, EditorialRow]
    pending_candidates: dict[str, int]
    memory: tuple[MemoryRow, ...]
