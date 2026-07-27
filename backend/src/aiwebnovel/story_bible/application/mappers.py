"""Explicit mapping from Story Bible aggregates to detached snapshots."""

from aiwebnovel.story_bible.application.models import StoryBibleSnapshot
from aiwebnovel.story_bible.entities import StoryBibleAggregate
from aiwebnovel.story_bible.errors import InvalidStoryBibleState


def story_bible_snapshot_from_aggregate(
    aggregate: StoryBibleAggregate,
) -> StoryBibleSnapshot:
    """Map every current aggregate field without reflection or side effects."""
    if type(aggregate) is not StoryBibleAggregate:
        raise InvalidStoryBibleState
    return StoryBibleSnapshot(
        story_bible_id=str(aggregate.story_bible.id),
        project_id=str(aggregate.story_bible.project_id),
        current_revision_id=str(aggregate.current_revision.id),
        revision_number=int(aggregate.current_revision.revision_number),
        concurrency_version=int(aggregate.story_bible.concurrency_version),
        title=str(aggregate.current_revision.title),
        content=str(aggregate.current_revision.content),
        created_at=aggregate.story_bible.created_at,
        updated_at=aggregate.story_bible.updated_at,
        revision_created_at=aggregate.current_revision.created_at,
        head_updated_at=aggregate.head.updated_at,
    )


__all__ = ["story_bible_snapshot_from_aggregate"]
