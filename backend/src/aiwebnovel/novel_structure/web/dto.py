"""Strict immutable HTTP DTOs for current novel-structure resources."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
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
    ManuscriptContent,
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)
from aiwebnovel.project.identifiers import ProjectId


class _StrictNovelStructureModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class CreateOutlineRequest(_StrictNovelStructureModel):
    title: str
    summary: str


class UpdateOutlineRequest(_StrictNovelStructureModel):
    title: str
    summary: str


class CreateVolumeRequest(_StrictNovelStructureModel):
    title: str
    summary: str
    position: int


class UpdateVolumeRequest(_StrictNovelStructureModel):
    title: str
    summary: str
    position: int


class CreateChapterRequest(_StrictNovelStructureModel):
    title: str
    summary: str
    position: int


class UpdateChapterRequest(_StrictNovelStructureModel):
    title: str
    summary: str
    position: int


class UpdateChapterContentRequest(_StrictNovelStructureModel):
    content: str


def _canonical(value: str, parser: Callable[[str], object], field: str) -> str:
    try:
        parsed = parser(value)
    except DomainError:
        raise ValueError(f"{field} must be canonical") from None
    if str(parsed) != value:
        raise ValueError(f"{field} must be canonical")
    return value


def _revision(value: int) -> int:
    try:
        return int(RevisionNumber(value))
    except DomainError:
        raise ValueError("revision_number must be positive") from None


def _version(value: int) -> int:
    try:
        return int(ConcurrencyVersion(value))
    except DomainError:
        raise ValueError("concurrency_version must be positive") from None


def _title(value: str) -> str:
    try:
        normalized = str(NovelStructureTitle(value))
    except DomainError:
        raise ValueError("title must satisfy novel-structure rules") from None
    if normalized != value:
        raise ValueError("title must be canonical")
    return value


def _summary(value: str) -> str:
    try:
        normalized = str(NovelStructureSummary(value))
    except DomainError:
        raise ValueError("summary must satisfy novel-structure rules") from None
    if normalized != value:
        raise ValueError("summary must be canonical")
    return value


def _position(value: int) -> int:
    try:
        return int(NovelStructurePosition(value))
    except DomainError:
        raise ValueError("position must be positive") from None


def _content(value: str) -> str:
    try:
        normalized = str(ManuscriptContent(value))
    except DomainError:
        raise ValueError("content must satisfy manuscript rules") from None
    if normalized != value:
        raise ValueError("content must use canonical LF line endings")
    return value


def _utc(value: datetime) -> datetime:
    try:
        normalized = ensure_utc(value)
    except (TypeError, ValueError):
        raise ValueError("response timestamps must be aware UTC") from None
    if value.utcoffset() != timedelta(0):
        raise ValueError("response timestamps must be UTC")
    return normalized


class _CurrentResponse(_StrictNovelStructureModel):
    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    summary: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime

    _project_id = field_validator("project_id")(
        lambda value: _canonical(value, ProjectId.parse, "project_id")
    )
    _revision_number = field_validator("revision_number")(_revision)
    _version = field_validator("concurrency_version")(_version)
    _title = field_validator("title")(_title)
    _summary = field_validator("summary")(_summary)
    _timestamps = field_validator("created_at", "updated_at", "revision_created_at")(_utc)

    @model_validator(mode="after")
    def require_consistent_state(self) -> Self:
        if self.revision_number != self.concurrency_version:
            raise ValueError("response versions must match")
        if self.created_at > self.updated_at or self.updated_at != self.revision_created_at:
            raise ValueError("response timestamps are inconsistent")
        return self


class OutlineResponse(_CurrentResponse):
    outline_id: str

    _outline_id = field_validator("outline_id")(
        lambda value: _canonical(value, OutlineId.parse, "outline_id")
    )
    _outline_revision_id = field_validator("current_revision_id")(
        lambda value: _canonical(value, OutlineRevisionId.parse, "current_revision_id")
    )


class VolumeResponse(_CurrentResponse):
    volume_id: str
    position: int

    _volume_id = field_validator("volume_id")(
        lambda value: _canonical(value, VolumeId.parse, "volume_id")
    )
    _volume_revision_id = field_validator("current_revision_id")(
        lambda value: _canonical(value, VolumeRevisionId.parse, "current_revision_id")
    )
    _position = field_validator("position")(_position)


class ChapterResponse(_CurrentResponse):
    chapter_id: str
    volume_id: str
    position: int

    _chapter_id = field_validator("chapter_id")(
        lambda value: _canonical(value, ChapterId.parse, "chapter_id")
    )
    _volume_id = field_validator("volume_id")(
        lambda value: _canonical(value, VolumeId.parse, "volume_id")
    )
    _chapter_revision_id = field_validator("current_revision_id")(
        lambda value: _canonical(value, ChapterRevisionId.parse, "current_revision_id")
    )
    _position = field_validator("position")(_position)


class ChapterContentResponse(_StrictNovelStructureModel):
    chapter_id: str
    project_id: str
    volume_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    content: str
    updated_at: datetime
    revision_created_at: datetime

    _chapter_id = field_validator("chapter_id")(
        lambda value: _canonical(value, ChapterId.parse, "chapter_id")
    )
    _project_id = field_validator("project_id")(
        lambda value: _canonical(value, ProjectId.parse, "project_id")
    )
    _volume_id = field_validator("volume_id")(
        lambda value: _canonical(value, VolumeId.parse, "volume_id")
    )
    _chapter_revision_id = field_validator("current_revision_id")(
        lambda value: _canonical(value, ChapterRevisionId.parse, "current_revision_id")
    )
    _revision_number = field_validator("revision_number")(_revision)
    _version = field_validator("concurrency_version")(_version)
    _content = field_validator("content")(_content)
    _timestamps = field_validator("updated_at", "revision_created_at")(_utc)

    @model_validator(mode="after")
    def require_consistent_state(self) -> Self:
        if self.revision_number != self.concurrency_version:
            raise ValueError("response versions must match")
        if self.updated_at != self.revision_created_at:
            raise ValueError("response timestamps are inconsistent")
        return self


__all__ = [
    "ChapterContentResponse",
    "ChapterResponse",
    "CreateChapterRequest",
    "CreateOutlineRequest",
    "CreateVolumeRequest",
    "OutlineResponse",
    "UpdateChapterContentRequest",
    "UpdateChapterRequest",
    "UpdateOutlineRequest",
    "UpdateVolumeRequest",
    "VolumeResponse",
]
