"""Detached immutable novel-structure application snapshots."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
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


def _canonical_identifier(
    value: object,
    *,
    field: str,
    parser: Callable[[str], object],
) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be a string")
    parsed = parser(value)
    if str(parsed) != value:
        raise ValueError(f"{field} must use its canonical representation")
    return value


def _positive_revision_number(value: object) -> int:
    if type(value) is not int:
        raise TypeError("revision_number must be an integer")
    return int(RevisionNumber(value))


def _positive_concurrency_version(value: object) -> int:
    if type(value) is not int:
        raise TypeError("concurrency_version must be an integer")
    return int(ConcurrencyVersion(value))


def _validated_title(value: object) -> str:
    if type(value) is not str:
        raise TypeError("title must be a string")
    return str(NovelStructureTitle(value))


def _validated_summary(value: object) -> str:
    if type(value) is not str:
        raise TypeError("summary must be a string")
    return str(NovelStructureSummary(value))


def _validated_position(value: object) -> int:
    if type(value) is not int:
        raise TypeError("position must be an integer")
    return int(NovelStructurePosition(value))


def _utc_datetime(value: object, *, field: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field} must be a datetime")
    try:
        return ensure_utc(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be timezone-aware") from None


def _validated_common(
    *,
    revision_number: object,
    concurrency_version: object,
    title: object,
    summary: object,
    created_at: object,
    updated_at: object,
    revision_created_at: object,
) -> tuple[int, int, str, str, datetime, datetime, datetime]:
    revision = _positive_revision_number(revision_number)
    version = _positive_concurrency_version(concurrency_version)
    if revision != version:
        raise ValueError("revision and concurrency versions must match")
    normalized_title = _validated_title(title)
    normalized_summary = _validated_summary(summary)
    created = _utc_datetime(created_at, field="created_at")
    updated = _utc_datetime(updated_at, field="updated_at")
    revision_created = _utc_datetime(
        revision_created_at,
        field="revision_created_at",
    )
    if created > updated or updated != revision_created:
        raise ValueError("novel-structure snapshot timestamps are inconsistent")
    return (
        revision,
        version,
        normalized_title,
        normalized_summary,
        created,
        updated,
        revision_created,
    )


@dataclass(frozen=True, slots=True)
class OutlineSnapshot:
    outline_id: str
    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    summary: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime

    def __post_init__(self) -> None:
        outline_id = _canonical_identifier(
            self.outline_id,
            field="outline_id",
            parser=OutlineId.parse,
        )
        project_id = _canonical_identifier(
            self.project_id,
            field="project_id",
            parser=ProjectId.parse,
        )
        revision_id = _canonical_identifier(
            self.current_revision_id,
            field="current_revision_id",
            parser=OutlineRevisionId.parse,
        )
        common = _validated_common(
            revision_number=self.revision_number,
            concurrency_version=self.concurrency_version,
            title=self.title,
            summary=self.summary,
            created_at=self.created_at,
            updated_at=self.updated_at,
            revision_created_at=self.revision_created_at,
        )
        _set_common(self, outline_id, project_id, revision_id, common)


@dataclass(frozen=True, slots=True)
class VolumeSnapshot:
    volume_id: str
    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    summary: str
    position: int
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime

    def __post_init__(self) -> None:
        volume_id = _canonical_identifier(
            self.volume_id,
            field="volume_id",
            parser=VolumeId.parse,
        )
        project_id = _canonical_identifier(
            self.project_id,
            field="project_id",
            parser=ProjectId.parse,
        )
        revision_id = _canonical_identifier(
            self.current_revision_id,
            field="current_revision_id",
            parser=VolumeRevisionId.parse,
        )
        common = _validated_common(
            revision_number=self.revision_number,
            concurrency_version=self.concurrency_version,
            title=self.title,
            summary=self.summary,
            created_at=self.created_at,
            updated_at=self.updated_at,
            revision_created_at=self.revision_created_at,
        )
        position = _validated_position(self.position)
        _set_common(self, volume_id, project_id, revision_id, common)
        object.__setattr__(self, "position", position)


@dataclass(frozen=True, slots=True)
class ChapterSnapshot:
    chapter_id: str
    project_id: str
    volume_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    summary: str
    position: int
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime

    def __post_init__(self) -> None:
        chapter_id = _canonical_identifier(
            self.chapter_id,
            field="chapter_id",
            parser=ChapterId.parse,
        )
        project_id = _canonical_identifier(
            self.project_id,
            field="project_id",
            parser=ProjectId.parse,
        )
        volume_id = _canonical_identifier(
            self.volume_id,
            field="volume_id",
            parser=VolumeId.parse,
        )
        revision_id = _canonical_identifier(
            self.current_revision_id,
            field="current_revision_id",
            parser=ChapterRevisionId.parse,
        )
        common = _validated_common(
            revision_number=self.revision_number,
            concurrency_version=self.concurrency_version,
            title=self.title,
            summary=self.summary,
            created_at=self.created_at,
            updated_at=self.updated_at,
            revision_created_at=self.revision_created_at,
        )
        position = _validated_position(self.position)
        _set_common(self, chapter_id, project_id, revision_id, common)
        object.__setattr__(self, "volume_id", volume_id)
        object.__setattr__(self, "position", position)


def _set_common(
    snapshot: OutlineSnapshot | VolumeSnapshot | ChapterSnapshot,
    stable_id: str,
    project_id: str,
    revision_id: str,
    common: tuple[int, int, str, str, datetime, datetime, datetime],
) -> None:
    revision, version, title, summary, created, updated, revision_created = common
    stable_field = {
        OutlineSnapshot: "outline_id",
        VolumeSnapshot: "volume_id",
        ChapterSnapshot: "chapter_id",
    }[type(snapshot)]
    object.__setattr__(snapshot, stable_field, stable_id)
    object.__setattr__(snapshot, "project_id", project_id)
    object.__setattr__(snapshot, "current_revision_id", revision_id)
    object.__setattr__(snapshot, "revision_number", revision)
    object.__setattr__(snapshot, "concurrency_version", version)
    object.__setattr__(snapshot, "title", title)
    object.__setattr__(snapshot, "summary", summary)
    object.__setattr__(snapshot, "created_at", created)
    object.__setattr__(snapshot, "updated_at", updated)
    object.__setattr__(snapshot, "revision_created_at", revision_created)


__all__ = ["ChapterSnapshot", "OutlineSnapshot", "VolumeSnapshot"]
