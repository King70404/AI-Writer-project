"""Framework-independent persistence contract for novel structure."""

from collections.abc import Callable
from typing import Protocol

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
from aiwebnovel.novel_structure.entities import (
    ChapterAggregate,
    OutlineAggregate,
    VolumeAggregate,
)
from aiwebnovel.novel_structure.identifiers import (
    ChapterId,
    ChapterRevisionId,
    OutlineId,
    OutlineRevisionId,
    VolumeId,
    VolumeRevisionId,
)
from aiwebnovel.novel_structure.values import (
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)
from aiwebnovel.project.identifiers import ProjectId


class NovelStructureRepository(Protocol):
    """Persist current Outline, Volume, and Chapter aggregates."""

    def create_outline(self, aggregate: OutlineAggregate) -> OutlineAggregate: ...

    def get_outline(self, outline_id: OutlineId) -> OutlineAggregate | None: ...

    def get_outline_for_project(self, project_id: ProjectId) -> OutlineAggregate | None: ...

    def append_outline_revision(
        self,
        outline_id: OutlineId,
        *,
        expected_version: ConcurrencyVersion,
        title: NovelStructureTitle,
        summary: NovelStructureSummary,
        clock: Clock,
        revision_id_factory: Callable[[], OutlineRevisionId],
    ) -> OutlineAggregate: ...

    def create_volume(self, aggregate: VolumeAggregate) -> VolumeAggregate: ...

    def get_volume(self, volume_id: VolumeId) -> VolumeAggregate | None: ...

    def list_volumes_for_project(self, project_id: ProjectId) -> tuple[VolumeAggregate, ...]: ...

    def append_volume_revision(
        self,
        volume_id: VolumeId,
        *,
        expected_version: ConcurrencyVersion,
        title: NovelStructureTitle,
        summary: NovelStructureSummary,
        position: NovelStructurePosition,
        clock: Clock,
        revision_id_factory: Callable[[], VolumeRevisionId],
    ) -> VolumeAggregate: ...

    def create_chapter(self, aggregate: ChapterAggregate) -> ChapterAggregate: ...

    def get_chapter(self, chapter_id: ChapterId) -> ChapterAggregate | None: ...

    def list_chapters_for_volume(self, volume_id: VolumeId) -> tuple[ChapterAggregate, ...]: ...

    def append_chapter_revision(
        self,
        chapter_id: ChapterId,
        *,
        expected_version: ConcurrencyVersion,
        title: NovelStructureTitle,
        summary: NovelStructureSummary,
        position: NovelStructurePosition,
        clock: Clock,
        revision_id_factory: Callable[[], ChapterRevisionId],
    ) -> ChapterAggregate: ...


__all__ = ["NovelStructureRepository"]
