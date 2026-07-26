"""Story Bible entity type, UTC, ownership, and aggregate invariant tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest
from tests.backend.story_bible_support import (
    BASE_TIME,
    initial_aggregate,
    project_id,
    revision_id,
    story_bible_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.entities import (
    StoryBible,
    StoryBibleAggregate,
    StoryBibleHead,
    StoryBibleRevision,
)
from aiwebnovel.story_bible.errors import InvalidStoryBibleState
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

CANARY = "STORY_BIBLE_SECRET_CANARY"


def _story_bible(
    *,
    identifier: StoryBibleId | None = None,
    owner: ProjectId | None = None,
    version: int = 1,
    created_at: datetime = BASE_TIME,
    updated_at: datetime = BASE_TIME,
) -> StoryBible:
    return StoryBible(
        id=story_bible_id() if identifier is None else identifier,
        project_id=project_id() if owner is None else owner,
        concurrency_version=ConcurrencyVersion(version),
        created_at=created_at,
        updated_at=updated_at,
    )


def _revision(
    *,
    identifier: StoryBibleRevisionId | None = None,
    owner: StoryBibleId | None = None,
    number: int = 1,
    title: str = "设定",
    content: str = "正文",
    created_at: datetime = BASE_TIME,
) -> StoryBibleRevision:
    return StoryBibleRevision(
        id=revision_id() if identifier is None else identifier,
        story_bible_id=story_bible_id() if owner is None else owner,
        revision_number=RevisionNumber(number),
        title=StoryBibleTitle(title),
        content=StoryBibleContent(content),
        created_at=created_at,
    )


def _head(
    *,
    owner: StoryBibleId | None = None,
    target: StoryBibleRevisionId | None = None,
    updated_at: datetime = BASE_TIME,
) -> StoryBibleHead:
    return StoryBibleHead(
        story_bible_id=story_bible_id() if owner is None else owner,
        revision_id=revision_id() if target is None else target,
        updated_at=updated_at,
    )


def test_each_entity_and_aggregate_accepts_one_valid_state() -> None:
    aggregate = initial_aggregate()

    assert aggregate.story_bible.id == story_bible_id()
    assert aggregate.story_bible.project_id == project_id()
    assert aggregate.head.revision_id == revision_id()
    assert aggregate.current_revision.revision_number == RevisionNumber(1)


def test_non_utc_aware_times_are_normalized_to_utc() -> None:
    local_time = datetime(2026, 7, 26, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    bible = _story_bible(created_at=local_time, updated_at=local_time)
    revision = _revision(created_at=local_time)
    head = _head(updated_at=local_time)

    assert bible.created_at == BASE_TIME
    assert bible.updated_at.tzinfo is UTC
    assert revision.created_at == BASE_TIME
    assert head.updated_at == BASE_TIME


@pytest.mark.parametrize(
    "changes",
    [
        {"id": revision_id()},
        {"project_id": story_bible_id()},
        {"concurrency_version": RevisionNumber()},
    ],
)
def test_story_bible_rejects_wrong_exact_field_types(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "id": story_bible_id(),
        "project_id": project_id(),
        "concurrency_version": ConcurrencyVersion(),
        "created_at": BASE_TIME,
        "updated_at": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidStoryBibleState):
        StoryBible(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
def test_story_bible_rejects_naive_or_non_datetime_time(field: str) -> None:
    arguments: dict[str, object] = {
        "id": story_bible_id(),
        "project_id": project_id(),
        "concurrency_version": ConcurrencyVersion(),
        "created_at": BASE_TIME,
        "updated_at": BASE_TIME,
    }
    arguments[field] = datetime(2026, 7, 26, 12, 0)
    with pytest.raises(InvalidStoryBibleState):
        StoryBible(**arguments)  # type: ignore[arg-type]

    arguments[field] = "2026-07-26T12:00:00Z"
    with pytest.raises(InvalidStoryBibleState):
        StoryBible(**arguments)  # type: ignore[arg-type]


def test_story_bible_rejects_creation_after_update() -> None:
    with pytest.raises(InvalidStoryBibleState):
        _story_bible(
            created_at=BASE_TIME + timedelta(seconds=1),
            updated_at=BASE_TIME,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"id": story_bible_id()},
        {"story_bible_id": revision_id()},
        {"revision_number": ConcurrencyVersion()},
        {"title": StoryBibleContent()},
        {"content": StoryBibleTitle("wrong")},
    ],
)
def test_revision_rejects_wrong_exact_field_types(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "id": revision_id(),
        "story_bible_id": story_bible_id(),
        "revision_number": RevisionNumber(),
        "title": StoryBibleTitle("设定"),
        "content": StoryBibleContent("正文"),
        "created_at": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidStoryBibleState):
        StoryBibleRevision(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("created_at", [datetime(2026, 7, 26, 12, 0), object()])
def test_revision_rejects_invalid_time(created_at: object) -> None:
    with pytest.raises(InvalidStoryBibleState):
        _revision(created_at=created_at)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"story_bible_id": revision_id()},
        {"revision_id": story_bible_id()},
    ],
)
def test_head_rejects_wrong_exact_field_types(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "story_bible_id": story_bible_id(),
        "revision_id": revision_id(),
        "updated_at": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidStoryBibleState):
        StoryBibleHead(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("updated_at", [datetime(2026, 7, 26, 12, 0), object()])
def test_head_rejects_invalid_time(updated_at: object) -> None:
    with pytest.raises(InvalidStoryBibleState):
        _head(updated_at=updated_at)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("story_bible", object()),
        ("head", object()),
        ("current_revision", object()),
    ],
)
def test_aggregate_rejects_wrong_exact_component_types(
    field: str,
    replacement: object,
) -> None:
    aggregate = initial_aggregate()
    arguments: dict[str, object] = {
        "story_bible": aggregate.story_bible,
        "head": aggregate.head,
        "current_revision": aggregate.current_revision,
    }
    arguments[field] = replacement

    with pytest.raises(InvalidStoryBibleState):
        StoryBibleAggregate(**arguments)  # type: ignore[arg-type]


def test_aggregate_rejects_head_owner_mismatch() -> None:
    aggregate = initial_aggregate()
    wrong_head = _head(owner=story_bible_id(20), target=aggregate.current_revision.id)

    with pytest.raises(InvalidStoryBibleState):
        replace(aggregate, head=wrong_head)


def test_aggregate_rejects_revision_owner_mismatch() -> None:
    aggregate = initial_aggregate()
    wrong_revision = _revision(
        identifier=aggregate.current_revision.id,
        owner=story_bible_id(20),
    )

    with pytest.raises(InvalidStoryBibleState):
        replace(aggregate, current_revision=wrong_revision)


def test_aggregate_rejects_head_revision_pointer_mismatch() -> None:
    aggregate = initial_aggregate()
    wrong_head = _head(owner=aggregate.story_bible.id, target=revision_id(20))

    with pytest.raises(InvalidStoryBibleState):
        replace(aggregate, head=wrong_head)


def test_aggregate_rejects_version_revision_number_mismatch() -> None:
    aggregate = initial_aggregate()
    wrong_bible = _story_bible(
        identifier=aggregate.story_bible.id,
        owner=aggregate.story_bible.project_id,
        version=2,
    )

    with pytest.raises(InvalidStoryBibleState):
        replace(aggregate, story_bible=wrong_bible)


def test_aggregate_rejects_story_bible_head_time_mismatch() -> None:
    aggregate = initial_aggregate()
    wrong_head = _head(
        owner=aggregate.story_bible.id,
        target=aggregate.current_revision.id,
        updated_at=BASE_TIME + timedelta(seconds=1),
    )

    with pytest.raises(InvalidStoryBibleState):
        replace(aggregate, head=wrong_head)


def test_aggregate_rejects_story_bible_revision_time_mismatch() -> None:
    aggregate = initial_aggregate()
    wrong_revision = _revision(
        identifier=aggregate.current_revision.id,
        owner=aggregate.story_bible.id,
        created_at=BASE_TIME + timedelta(seconds=1),
    )

    with pytest.raises(InvalidStoryBibleState):
        replace(aggregate, current_revision=wrong_revision)


def test_aggregate_rejects_revision_before_story_bible_creation() -> None:
    bible_id = story_bible_id()
    rev_id = revision_id()
    revision_time = BASE_TIME
    bible = _story_bible(
        identifier=bible_id,
        created_at=revision_time + timedelta(seconds=1),
        updated_at=revision_time + timedelta(seconds=1),
    )
    revision = _revision(
        identifier=rev_id,
        owner=bible_id,
        created_at=revision_time,
    )
    head = _head(
        owner=bible_id,
        target=rev_id,
        updated_at=bible.updated_at,
    )

    with pytest.raises(InvalidStoryBibleState):
        StoryBibleAggregate(
            story_bible=bible,
            head=head,
            current_revision=revision,
        )


def test_invalid_aggregate_error_never_leaks_title_or_content() -> None:
    aggregate = initial_aggregate(title=CANARY, content=CANARY)
    wrong_head = _head(owner=story_bible_id(20), target=aggregate.current_revision.id)

    with pytest.raises(InvalidStoryBibleState) as caught:
        replace(aggregate, head=wrong_head)

    assert CANARY not in str(caught.value)
    assert CANARY not in repr(caught.value)
