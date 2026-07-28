"""Story Bible immutable revision-history query service."""

from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.story_bible.application.errors import (
    StoryBibleRevisionNotFound,
)
from aiwebnovel.story_bible.application.history_models import (
    StoryBibleRevisionHistoryPage,
    StoryBibleRevisionSnapshot,
)
from aiwebnovel.story_bible.application.history_queries import (
    GetStoryBibleRevisionQuery,
    ListStoryBibleRevisionsQuery,
    validate_story_bible_revision_history_limit,
)
from aiwebnovel.story_bible.application.history_reader import (
    StoryBibleRevisionHistoryReader,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId


class StoryBibleRevisionHistoryQueryService:
    """Read immutable revisions only through the dedicated history port."""

    def __init__(self, reader: StoryBibleRevisionHistoryReader) -> None:
        self._reader = reader

    def list_revisions(
        self,
        query: ListStoryBibleRevisionsQuery,
    ) -> StoryBibleRevisionHistoryPage:
        """Validate one query and call the reader exactly once."""
        if type(query) is not ListStoryBibleRevisionsQuery:
            raise TypeError("query must be a ListStoryBibleRevisionsQuery")
        story_bible_id = StoryBibleId.parse(query.story_bible_id)
        limit = validate_story_bible_revision_history_limit(query.limit)
        if query.after is not None and query.after.story_bible_id != story_bible_id:
            raise ValueError("after position must belong to the requested Story Bible")
        return self._reader.list_revisions(
            story_bible_id,
            limit=limit,
            after=query.after,
        )

    def get_revision(
        self,
        query: GetStoryBibleRevisionQuery,
    ) -> StoryBibleRevisionSnapshot:
        """Return one exact revision or distinguish its absence safely."""
        if type(query) is not GetStoryBibleRevisionQuery:
            raise TypeError("query must be a GetStoryBibleRevisionQuery")
        story_bible_id = StoryBibleId.parse(query.story_bible_id)
        revision_number = RevisionNumber(query.revision_number)
        snapshot = self._reader.get_revision(story_bible_id, revision_number)
        if snapshot is None:
            raise StoryBibleRevisionNotFound(story_bible_id, revision_number)
        return snapshot


__all__ = ["StoryBibleRevisionHistoryQueryService"]
