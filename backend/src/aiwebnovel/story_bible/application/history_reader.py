"""Pure read port for immutable Story Bible revision history."""

from typing import Protocol

from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.story_bible.application.history_models import (
    StoryBibleRevisionHistoryPage,
    StoryBibleRevisionHistoryPosition,
    StoryBibleRevisionSnapshot,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId


class StoryBibleRevisionHistoryReader(Protocol):
    """Read immutable revisions without exposing persistence objects."""

    def list_revisions(
        self,
        story_bible_id: StoryBibleId,
        *,
        limit: int,
        after: StoryBibleRevisionHistoryPosition | None,
    ) -> StoryBibleRevisionHistoryPage: ...

    def get_revision(
        self,
        story_bible_id: StoryBibleId,
        revision_number: RevisionNumber,
    ) -> StoryBibleRevisionSnapshot | None: ...


__all__ = ["StoryBibleRevisionHistoryReader"]
