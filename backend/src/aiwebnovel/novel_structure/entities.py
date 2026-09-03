"""Immutable Outline, Volume, and Chapter entities and aggregate invariants."""

from dataclasses import dataclass, field
from datetime import datetime

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.novel_structure.errors import InvalidNovelStructureState
from aiwebnovel.novel_structure.identifiers import (
    ChapterId,
    ChapterRevisionId,
    OutlineId,
    OutlineRevisionId,
    VolumeId,
    VolumeRevisionId,
)
from aiwebnovel.novel_structure.values import (
    ManuscriptContent,
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)
from aiwebnovel.project.identifiers import ProjectId


def normalize_novel_structure_time(value: object) -> datetime:
    """Normalize an exact datetime to UTC without retaining invalid input."""
    if type(value) is not datetime:
        raise InvalidNovelStructureState
    try:
        return ensure_utc(value)
    except ValueError:
        raise InvalidNovelStructureState from None


@dataclass(frozen=True, slots=True)
class Outline:
    """Stable Outline identity and owning Project."""

    id: OutlineId
    project_id: ProjectId
    concurrency_version: ConcurrencyVersion
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not OutlineId
            or type(self.project_id) is not ProjectId
            or type(self.concurrency_version) is not ConcurrencyVersion
        ):
            raise InvalidNovelStructureState
        created_at = normalize_novel_structure_time(self.created_at)
        updated_at = normalize_novel_structure_time(self.updated_at)
        if updated_at < created_at:
            raise InvalidNovelStructureState
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


@dataclass(frozen=True, slots=True)
class OutlineRevision:
    """One immutable complete Outline snapshot."""

    id: OutlineRevisionId
    outline_id: OutlineId
    revision_number: RevisionNumber
    title: NovelStructureTitle
    summary: NovelStructureSummary
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not OutlineRevisionId
            or type(self.outline_id) is not OutlineId
            or type(self.revision_number) is not RevisionNumber
            or type(self.title) is not NovelStructureTitle
            or type(self.summary) is not NovelStructureSummary
        ):
            raise InvalidNovelStructureState
        object.__setattr__(self, "created_at", normalize_novel_structure_time(self.created_at))


@dataclass(frozen=True, slots=True)
class OutlineHead:
    """The authoritative pointer to one current Outline revision."""

    outline_id: OutlineId
    revision_id: OutlineRevisionId
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.outline_id) is not OutlineId
            or type(self.revision_id) is not OutlineRevisionId
        ):
            raise InvalidNovelStructureState
        object.__setattr__(self, "updated_at", normalize_novel_structure_time(self.updated_at))


@dataclass(frozen=True, slots=True)
class OutlineAggregate:
    """A consistent current Outline view without revision history."""

    outline: Outline
    head: OutlineHead
    current_revision: OutlineRevision

    def __post_init__(self) -> None:
        if (
            type(self.outline) is not Outline
            or type(self.head) is not OutlineHead
            or type(self.current_revision) is not OutlineRevision
            or self.head.outline_id != self.outline.id
            or self.current_revision.outline_id != self.outline.id
            or self.head.revision_id != self.current_revision.id
            or self.outline.concurrency_version.value != self.current_revision.revision_number.value
            or self.outline.updated_at != self.head.updated_at
            or self.outline.updated_at != self.current_revision.created_at
        ):
            raise InvalidNovelStructureState


@dataclass(frozen=True, slots=True)
class Volume:
    """Stable Volume identity and owning Project."""

    id: VolumeId
    project_id: ProjectId
    concurrency_version: ConcurrencyVersion
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not VolumeId
            or type(self.project_id) is not ProjectId
            or type(self.concurrency_version) is not ConcurrencyVersion
        ):
            raise InvalidNovelStructureState
        created_at = normalize_novel_structure_time(self.created_at)
        updated_at = normalize_novel_structure_time(self.updated_at)
        if updated_at < created_at:
            raise InvalidNovelStructureState
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


@dataclass(frozen=True, slots=True)
class VolumeRevision:
    """One immutable complete Volume snapshot."""

    id: VolumeRevisionId
    volume_id: VolumeId
    revision_number: RevisionNumber
    title: NovelStructureTitle
    summary: NovelStructureSummary
    position: NovelStructurePosition
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not VolumeRevisionId
            or type(self.volume_id) is not VolumeId
            or type(self.revision_number) is not RevisionNumber
            or type(self.title) is not NovelStructureTitle
            or type(self.summary) is not NovelStructureSummary
            or type(self.position) is not NovelStructurePosition
        ):
            raise InvalidNovelStructureState
        object.__setattr__(self, "created_at", normalize_novel_structure_time(self.created_at))


@dataclass(frozen=True, slots=True)
class VolumeHead:
    """The authoritative pointer to one current Volume revision."""

    volume_id: VolumeId
    revision_id: VolumeRevisionId
    updated_at: datetime

    def __post_init__(self) -> None:
        if type(self.volume_id) is not VolumeId or type(self.revision_id) is not VolumeRevisionId:
            raise InvalidNovelStructureState
        object.__setattr__(self, "updated_at", normalize_novel_structure_time(self.updated_at))


@dataclass(frozen=True, slots=True)
class VolumeAggregate:
    """A consistent current Volume view without revision history."""

    volume: Volume
    head: VolumeHead
    current_revision: VolumeRevision

    def __post_init__(self) -> None:
        if (
            type(self.volume) is not Volume
            or type(self.head) is not VolumeHead
            or type(self.current_revision) is not VolumeRevision
            or self.head.volume_id != self.volume.id
            or self.current_revision.volume_id != self.volume.id
            or self.head.revision_id != self.current_revision.id
            or self.volume.concurrency_version.value != self.current_revision.revision_number.value
            or self.volume.updated_at != self.head.updated_at
            or self.volume.updated_at != self.current_revision.created_at
        ):
            raise InvalidNovelStructureState


@dataclass(frozen=True, slots=True)
class Chapter:
    """Stable Chapter identity and immutable Project/Volume ownership."""

    id: ChapterId
    project_id: ProjectId
    volume_id: VolumeId
    concurrency_version: ConcurrencyVersion
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not ChapterId
            or type(self.project_id) is not ProjectId
            or type(self.volume_id) is not VolumeId
            or type(self.concurrency_version) is not ConcurrencyVersion
        ):
            raise InvalidNovelStructureState
        created_at = normalize_novel_structure_time(self.created_at)
        updated_at = normalize_novel_structure_time(self.updated_at)
        if updated_at < created_at:
            raise InvalidNovelStructureState
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


@dataclass(frozen=True, slots=True)
class ChapterRevision:
    """One immutable complete Chapter structure and manuscript snapshot."""

    id: ChapterRevisionId
    chapter_id: ChapterId
    revision_number: RevisionNumber
    title: NovelStructureTitle
    summary: NovelStructureSummary
    position: NovelStructurePosition
    created_at: datetime
    content: ManuscriptContent = field(default_factory=ManuscriptContent)

    def __post_init__(self) -> None:
        if (
            type(self.id) is not ChapterRevisionId
            or type(self.chapter_id) is not ChapterId
            or type(self.revision_number) is not RevisionNumber
            or type(self.title) is not NovelStructureTitle
            or type(self.summary) is not NovelStructureSummary
            or type(self.position) is not NovelStructurePosition
            or type(self.content) is not ManuscriptContent
        ):
            raise InvalidNovelStructureState
        object.__setattr__(self, "created_at", normalize_novel_structure_time(self.created_at))


@dataclass(frozen=True, slots=True)
class ChapterHead:
    """The authoritative pointer to one current Chapter revision."""

    chapter_id: ChapterId
    revision_id: ChapterRevisionId
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.chapter_id) is not ChapterId
            or type(self.revision_id) is not ChapterRevisionId
        ):
            raise InvalidNovelStructureState
        object.__setattr__(self, "updated_at", normalize_novel_structure_time(self.updated_at))


@dataclass(frozen=True, slots=True)
class ChapterAggregate:
    """A consistent current Chapter view without revision history."""

    chapter: Chapter
    head: ChapterHead
    current_revision: ChapterRevision

    def __post_init__(self) -> None:
        if (
            type(self.chapter) is not Chapter
            or type(self.head) is not ChapterHead
            or type(self.current_revision) is not ChapterRevision
            or self.head.chapter_id != self.chapter.id
            or self.current_revision.chapter_id != self.chapter.id
            or self.head.revision_id != self.current_revision.id
            or self.chapter.concurrency_version.value != self.current_revision.revision_number.value
            or self.chapter.updated_at != self.head.updated_at
            or self.chapter.updated_at != self.current_revision.created_at
        ):
            raise InvalidNovelStructureState


def assert_chapter_belongs_to_volume(chapter: Chapter, volume: Volume) -> None:
    """Require a Chapter and Volume to share both identity and Project ownership."""
    if (
        type(chapter) is not Chapter
        or type(volume) is not Volume
        or chapter.volume_id != volume.id
        or chapter.project_id != volume.project_id
    ):
        raise InvalidNovelStructureState
