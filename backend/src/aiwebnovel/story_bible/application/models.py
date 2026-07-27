"""Detached Story Bible application snapshots made only from safe primitives."""

from dataclasses import dataclass
from datetime import datetime

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle


def _canonical_identifier(
    value: object,
    *,
    field: str,
    identifier_type: type[StoryBibleId] | type[StoryBibleRevisionId] | type[ProjectId],
) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be a string")
    parsed = identifier_type.parse(value)
    canonical = str(parsed)
    if canonical != value:
        raise ValueError(f"{field} must use its canonical representation")
    return canonical


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
    return str(StoryBibleTitle(value))


def _validated_content(value: object) -> str:
    if type(value) is not str:
        raise TypeError("content must be a string")
    return str(StoryBibleContent(value))


def _utc_datetime(value: object, *, field: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field} must be a datetime")
    try:
        return ensure_utc(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be timezone-aware") from None


@dataclass(frozen=True, slots=True)
class StoryBibleSnapshot:
    """Immutable current Story Bible state detached from domain and persistence."""

    story_bible_id: str
    project_id: str
    current_revision_id: str
    revision_number: int
    concurrency_version: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
    revision_created_at: datetime
    head_updated_at: datetime

    def __post_init__(self) -> None:
        story_bible_id = _canonical_identifier(
            self.story_bible_id,
            field="story_bible_id",
            identifier_type=StoryBibleId,
        )
        project_id = _canonical_identifier(
            self.project_id,
            field="project_id",
            identifier_type=ProjectId,
        )
        current_revision_id = _canonical_identifier(
            self.current_revision_id,
            field="current_revision_id",
            identifier_type=StoryBibleRevisionId,
        )
        revision_number = _positive_revision_number(self.revision_number)
        concurrency_version = _positive_concurrency_version(self.concurrency_version)
        if revision_number != concurrency_version:
            raise ValueError("revision and concurrency versions must match")
        title = _validated_title(self.title)
        content = _validated_content(self.content)
        created_at = _utc_datetime(self.created_at, field="created_at")
        updated_at = _utc_datetime(self.updated_at, field="updated_at")
        revision_created_at = _utc_datetime(
            self.revision_created_at,
            field="revision_created_at",
        )
        head_updated_at = _utc_datetime(
            self.head_updated_at,
            field="head_updated_at",
        )
        if (
            created_at > updated_at
            or updated_at != revision_created_at
            or updated_at != head_updated_at
        ):
            raise ValueError("Story Bible snapshot timestamps are inconsistent")
        object.__setattr__(self, "story_bible_id", story_bible_id)
        object.__setattr__(self, "project_id", project_id)
        object.__setattr__(self, "current_revision_id", current_revision_id)
        object.__setattr__(self, "revision_number", revision_number)
        object.__setattr__(self, "concurrency_version", concurrency_version)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "revision_created_at", revision_created_at)
        object.__setattr__(self, "head_updated_at", head_updated_at)


__all__ = ["StoryBibleSnapshot"]
