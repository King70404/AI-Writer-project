"""Story Bible SQLAlchemy persistence adapters."""

from aiwebnovel.story_bible.persistence.history_reader import (
    SqlAlchemyStoryBibleRevisionHistoryReader,
)

__all__ = ["SqlAlchemyStoryBibleRevisionHistoryReader"]
