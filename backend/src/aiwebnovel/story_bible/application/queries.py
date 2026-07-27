"""Immutable primitive inputs for Story Bible current-snapshot queries."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetStoryBibleQuery:
    """Request the current snapshot for one Story Bible identifier."""

    story_bible_id: str


@dataclass(frozen=True, slots=True)
class GetStoryBibleForProjectQuery:
    """Request the unique current Story Bible owned by one Project."""

    project_id: str


__all__ = ["GetStoryBibleForProjectQuery", "GetStoryBibleQuery"]
