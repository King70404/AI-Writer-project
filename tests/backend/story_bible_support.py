"""Deterministic test values for the pure Story Bible domain."""

from datetime import UTC, datetime

from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible import (
    StoryBibleAggregate,
    StoryBibleContent,
    StoryBibleId,
    StoryBibleRevisionId,
    StoryBibleTitle,
    create_initial_story_bible,
)

BASE_TIME = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def project_id(randomness: int = 1) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_parts(1, randomness))


def story_bible_id(randomness: int = 2) -> StoryBibleId:
    return StoryBibleId.from_ulid(Ulid.from_parts(1, randomness))


def revision_id(randomness: int = 3) -> StoryBibleRevisionId:
    return StoryBibleRevisionId.from_ulid(Ulid.from_parts(1, randomness))


def initial_aggregate(
    *,
    title: str = "都市异能设定",
    content: str = "力量有代价。",
) -> StoryBibleAggregate:
    return create_initial_story_bible(
        story_bible_id=story_bible_id(),
        revision_id=revision_id(),
        project_id=project_id(),
        title=StoryBibleTitle(title),
        content=StoryBibleContent(content),
        now=BASE_TIME,
    )
