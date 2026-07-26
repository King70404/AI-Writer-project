"""Immutable Story Bible entities and current-aggregate invariants."""

from dataclasses import dataclass
from datetime import datetime

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.errors import InvalidStoryBibleState
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle


def normalize_story_bible_time(value: object) -> datetime:
    """Normalize an exact datetime to UTC without retaining invalid input."""
    if type(value) is not datetime:
        raise InvalidStoryBibleState
    try:
        return ensure_utc(value)
    except (TypeError, ValueError):
        raise InvalidStoryBibleState from None


@dataclass(frozen=True, slots=True)
class StoryBible:
    """Stable Story Bible identity, Project ownership, and concurrency state."""

    id: StoryBibleId
    project_id: ProjectId
    concurrency_version: ConcurrencyVersion
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not StoryBibleId
            or type(self.project_id) is not ProjectId
            or type(self.concurrency_version) is not ConcurrencyVersion
        ):
            raise InvalidStoryBibleState
        created_at = normalize_story_bible_time(self.created_at)
        updated_at = normalize_story_bible_time(self.updated_at)
        if updated_at < created_at:
            raise InvalidStoryBibleState
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


@dataclass(frozen=True, slots=True)
class StoryBibleRevision:
    """One immutable complete text snapshot for a Story Bible."""

    id: StoryBibleRevisionId
    story_bible_id: StoryBibleId
    revision_number: RevisionNumber
    title: StoryBibleTitle
    content: StoryBibleContent
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.id) is not StoryBibleRevisionId
            or type(self.story_bible_id) is not StoryBibleId
            or type(self.revision_number) is not RevisionNumber
            or type(self.title) is not StoryBibleTitle
            or type(self.content) is not StoryBibleContent
        ):
            raise InvalidStoryBibleState
        object.__setattr__(
            self,
            "created_at",
            normalize_story_bible_time(self.created_at),
        )


@dataclass(frozen=True, slots=True)
class StoryBibleHead:
    """The authoritative pointer to one current immutable revision."""

    story_bible_id: StoryBibleId
    revision_id: StoryBibleRevisionId
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.story_bible_id) is not StoryBibleId
            or type(self.revision_id) is not StoryBibleRevisionId
        ):
            raise InvalidStoryBibleState
        object.__setattr__(
            self,
            "updated_at",
            normalize_story_bible_time(self.updated_at),
        )


@dataclass(frozen=True, slots=True)
class StoryBibleAggregate:
    """A consistent current view without embedding revision history."""

    story_bible: StoryBible
    head: StoryBibleHead
    current_revision: StoryBibleRevision

    def __post_init__(self) -> None:
        if (
            type(self.story_bible) is not StoryBible
            or type(self.head) is not StoryBibleHead
            or type(self.current_revision) is not StoryBibleRevision
            or self.head.story_bible_id != self.story_bible.id
            or self.current_revision.story_bible_id != self.story_bible.id
            or self.head.revision_id != self.current_revision.id
            or self.story_bible.concurrency_version.value
            != self.current_revision.revision_number.value
            or self.story_bible.updated_at != self.head.updated_at
            or self.story_bible.updated_at != self.current_revision.created_at
            or self.story_bible.created_at > self.story_bible.updated_at
            or self.current_revision.created_at < self.story_bible.created_at
        ):
            raise InvalidStoryBibleState
