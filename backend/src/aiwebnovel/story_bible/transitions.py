"""Pure Story Bible creation and immutable revision transitions."""

from datetime import datetime

from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.entities import (
    StoryBible,
    StoryBibleAggregate,
    StoryBibleHead,
    StoryBibleRevision,
    normalize_story_bible_time,
)
from aiwebnovel.story_bible.errors import InvalidStoryBibleState
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle


def create_initial_story_bible(
    *,
    story_bible_id: StoryBibleId,
    revision_id: StoryBibleRevisionId,
    project_id: ProjectId,
    title: StoryBibleTitle,
    content: StoryBibleContent,
    now: datetime,
) -> StoryBibleAggregate:
    """Create revision one from caller-supplied values without side effects."""
    if (
        type(story_bible_id) is not StoryBibleId
        or type(revision_id) is not StoryBibleRevisionId
        or type(project_id) is not ProjectId
        or type(title) is not StoryBibleTitle
        or type(content) is not StoryBibleContent
    ):
        raise InvalidStoryBibleState
    normalized_now = normalize_story_bible_time(now)
    story_bible = StoryBible(
        id=story_bible_id,
        project_id=project_id,
        concurrency_version=ConcurrencyVersion(),
        created_at=normalized_now,
        updated_at=normalized_now,
    )
    revision = StoryBibleRevision(
        id=revision_id,
        story_bible_id=story_bible_id,
        revision_number=RevisionNumber(),
        title=title,
        content=content,
        created_at=normalized_now,
    )
    head = StoryBibleHead(
        story_bible_id=story_bible_id,
        revision_id=revision_id,
        updated_at=normalized_now,
    )
    return StoryBibleAggregate(
        story_bible=story_bible,
        head=head,
        current_revision=revision,
    )


def append_story_bible_revision(
    aggregate: StoryBibleAggregate,
    *,
    expected_version: ConcurrencyVersion,
    revision_id: StoryBibleRevisionId,
    title: StoryBibleTitle,
    content: StoryBibleContent,
    now: datetime,
) -> StoryBibleAggregate:
    """Append one complete revision after an optimistic-concurrency check."""
    if type(aggregate) is not StoryBibleAggregate:
        raise InvalidStoryBibleState
    assert_expected_version(
        actual=aggregate.story_bible.concurrency_version,
        expected=expected_version,
    )
    if (
        type(revision_id) is not StoryBibleRevisionId
        or type(title) is not StoryBibleTitle
        or type(content) is not StoryBibleContent
    ):
        raise InvalidStoryBibleState
    normalized_now = normalize_story_bible_time(now)
    if normalized_now < aggregate.story_bible.updated_at:
        raise InvalidStoryBibleState
    if revision_id == aggregate.current_revision.id:
        raise InvalidStoryBibleState

    story_bible = StoryBible(
        id=aggregate.story_bible.id,
        project_id=aggregate.story_bible.project_id,
        concurrency_version=aggregate.story_bible.concurrency_version.next(),
        created_at=aggregate.story_bible.created_at,
        updated_at=normalized_now,
    )
    revision = StoryBibleRevision(
        id=revision_id,
        story_bible_id=aggregate.story_bible.id,
        revision_number=aggregate.current_revision.revision_number.next(),
        title=title,
        content=content,
        created_at=normalized_now,
    )
    head = StoryBibleHead(
        story_bible_id=aggregate.story_bible.id,
        revision_id=revision_id,
        updated_at=normalized_now,
    )
    return StoryBibleAggregate(
        story_bible=story_bible,
        head=head,
        current_revision=revision,
    )
