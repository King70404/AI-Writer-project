"""Framework-independent persistence contract owned by Story Bible."""

from collections.abc import Callable
from typing import Protocol

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.entities import StoryBibleAggregate
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle


class StoryBibleRepository(Protocol):
    """Store and restore only the current Story Bible aggregate."""

    def create(self, aggregate: StoryBibleAggregate) -> StoryBibleAggregate:
        """Atomically persist a stable object, revision one, and its head."""
        ...

    def get(self, story_bible_id: StoryBibleId) -> StoryBibleAggregate | None:
        """Return one consistent current aggregate, or None when absent."""
        ...

    def get_for_project(self, project_id: ProjectId) -> StoryBibleAggregate | None:
        """Return a Project's unique Story Bible, or None when it has none."""
        ...

    def append_revision(
        self,
        story_bible_id: StoryBibleId,
        *,
        expected_version: ConcurrencyVersion,
        title: StoryBibleTitle,
        content: StoryBibleContent,
        clock: Clock,
        revision_id_factory: Callable[[], StoryBibleRevisionId],
    ) -> StoryBibleAggregate:
        """Atomically append a complete revision using stable and head CAS."""
        ...


__all__ = ["StoryBibleRepository"]
