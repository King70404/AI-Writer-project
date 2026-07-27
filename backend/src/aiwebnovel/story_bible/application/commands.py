"""Immutable primitive inputs for Story Bible write use cases."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateStoryBibleCommand:
    """Request creation of one Project-owned Story Bible."""

    project_id: str
    title: str
    content: str


@dataclass(frozen=True, slots=True)
class ReviseStoryBibleCommand:
    """Replace the complete current Story Bible title and content."""

    story_bible_id: str
    expected_version: int
    title: str
    content: str


__all__ = ["CreateStoryBibleCommand", "ReviseStoryBibleCommand"]
