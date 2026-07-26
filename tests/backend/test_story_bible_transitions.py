"""Pure Story Bible creation, append, conflict, and sequence tests."""

from datetime import timedelta, timezone

import pytest
from tests.backend.story_bible_support import (
    BASE_TIME,
    initial_aggregate,
    project_id,
    revision_id,
    story_bible_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import (
    ConcurrencyConflict,
    InvalidConcurrencyVersion,
)
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.story_bible import (
    InvalidStoryBibleState,
    StoryBibleContent,
    StoryBibleTitle,
    append_story_bible_revision,
    create_initial_story_bible,
)

CANARY = "STORY_BIBLE_SECRET_CANARY"


def test_initial_creation_uses_supplied_identity_content_and_one_instant() -> None:
    bible_id = story_bible_id()
    rev_id = revision_id()
    owner = project_id()
    title = StoryBibleTitle("设定标题")
    content = StoryBibleContent("完整正文")

    aggregate = create_initial_story_bible(
        story_bible_id=bible_id,
        revision_id=rev_id,
        project_id=owner,
        title=title,
        content=content,
        now=BASE_TIME,
    )

    assert aggregate.story_bible.id is bible_id
    assert aggregate.story_bible.project_id is owner
    assert aggregate.story_bible.concurrency_version == ConcurrencyVersion(1)
    assert aggregate.story_bible.created_at == BASE_TIME
    assert aggregate.story_bible.updated_at == BASE_TIME
    assert aggregate.current_revision.id is rev_id
    assert aggregate.current_revision.revision_number == RevisionNumber(1)
    assert aggregate.current_revision.title is title
    assert aggregate.current_revision.content is content
    assert aggregate.current_revision.created_at == BASE_TIME
    assert aggregate.head.story_bible_id is bible_id
    assert aggregate.head.revision_id is rev_id
    assert aggregate.head.updated_at == BASE_TIME
    assert title == StoryBibleTitle("设定标题")
    assert content == StoryBibleContent("完整正文")


def test_initial_creation_normalizes_non_utc_aware_time() -> None:
    local_time = BASE_TIME.astimezone(timezone(timedelta(hours=8)))

    aggregate = create_initial_story_bible(
        story_bible_id=story_bible_id(),
        revision_id=revision_id(),
        project_id=project_id(),
        title=StoryBibleTitle("设定"),
        content=StoryBibleContent(),
        now=local_time,
    )

    assert aggregate.story_bible.created_at == BASE_TIME
    assert aggregate.head.updated_at == BASE_TIME


@pytest.mark.parametrize(
    "changes",
    [
        {"story_bible_id": revision_id()},
        {"revision_id": story_bible_id()},
        {"project_id": story_bible_id()},
        {"title": StoryBibleContent()},
        {"content": StoryBibleTitle("wrong")},
    ],
)
def test_initial_creation_rejects_wrong_domain_object_types(
    changes: dict[str, object],
) -> None:
    arguments: dict[str, object] = {
        "story_bible_id": story_bible_id(),
        "revision_id": revision_id(),
        "project_id": project_id(),
        "title": StoryBibleTitle("设定"),
        "content": StoryBibleContent(),
        "now": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidStoryBibleState):
        create_initial_story_bible(**arguments)  # type: ignore[arg-type]


def test_initial_creation_rejects_naive_time() -> None:
    with pytest.raises(InvalidStoryBibleState):
        create_initial_story_bible(
            story_bible_id=story_bible_id(),
            revision_id=revision_id(),
            project_id=project_id(),
            title=StoryBibleTitle("设定"),
            content=StoryBibleContent(),
            now=BASE_TIME.replace(tzinfo=None),
        )


def test_append_creates_a_complete_replacement_and_preserves_identity() -> None:
    old = initial_aggregate(title="旧标题", content="旧正文")
    new_revision_id = revision_id(4)
    new_title = StoryBibleTitle("新标题")
    new_content = StoryBibleContent("新正文")
    now = BASE_TIME + timedelta(seconds=1)

    new = append_story_bible_revision(
        old,
        expected_version=ConcurrencyVersion(1),
        revision_id=new_revision_id,
        title=new_title,
        content=new_content,
        now=now,
    )

    assert new is not old
    assert new.story_bible.id is old.story_bible.id
    assert new.story_bible.project_id is old.story_bible.project_id
    assert new.story_bible.created_at == old.story_bible.created_at
    assert new.story_bible.updated_at == now
    assert new.story_bible.concurrency_version == ConcurrencyVersion(2)
    assert new.current_revision.id is new_revision_id
    assert new.current_revision.revision_number == RevisionNumber(2)
    assert new.current_revision.title is new_title
    assert new.current_revision.content is new_content
    assert new.head.revision_id is new_revision_id
    assert new.head.updated_at == now


def test_append_allows_equal_time_and_empty_content_as_explicit_replacement() -> None:
    old = initial_aggregate(content="不得继承")

    new = append_story_bible_revision(
        old,
        expected_version=ConcurrencyVersion(1),
        revision_id=revision_id(4),
        title=StoryBibleTitle("完整新标题"),
        content=StoryBibleContent(""),
        now=old.story_bible.updated_at,
    )

    assert str(new.current_revision.content) == ""
    assert str(new.current_revision.title) == "完整新标题"
    assert str(old.current_revision.content) == "不得继承"


def test_append_rejects_wrong_aggregate_type() -> None:
    with pytest.raises(InvalidStoryBibleState):
        append_story_bible_revision(
            object(),  # type: ignore[arg-type]
            expected_version=ConcurrencyVersion(1),
            revision_id=revision_id(4),
            title=StoryBibleTitle("设定"),
            content=StoryBibleContent(),
            now=BASE_TIME,
        )


@pytest.mark.parametrize("expected", [True, 1.0])
def test_append_rejects_non_version_expected_values(expected: object) -> None:
    with pytest.raises(InvalidConcurrencyVersion):
        append_story_bible_revision(
            initial_aggregate(),
            expected_version=expected,  # type: ignore[arg-type]
            revision_id=revision_id(4),
            title=StoryBibleTitle("设定"),
            content=StoryBibleContent(),
            now=BASE_TIME,
        )


def test_stale_conflict_preserves_expected_actual_and_has_highest_priority() -> None:
    aggregate = initial_aggregate(title=CANARY, content=CANARY)

    with pytest.raises(ConcurrencyConflict) as caught:
        append_story_bible_revision(
            aggregate,
            expected_version=ConcurrencyVersion(2),
            revision_id=aggregate.current_revision.id,
            title=StoryBibleTitle("新设定"),
            content=StoryBibleContent("新正文"),
            now=BASE_TIME - timedelta(seconds=1),
        )

    assert caught.value.expected_version == 2
    assert caught.value.actual_version == 1
    assert CANARY not in str(caught.value)
    assert CANARY not in repr(caught.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"revision_id": story_bible_id()},
        {"title": StoryBibleContent()},
        {"content": StoryBibleTitle("wrong")},
    ],
)
def test_append_rejects_wrong_new_revision_field_types(
    changes: dict[str, object],
) -> None:
    arguments: dict[str, object] = {
        "expected_version": ConcurrencyVersion(1),
        "revision_id": revision_id(4),
        "title": StoryBibleTitle("设定"),
        "content": StoryBibleContent(),
        "now": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidStoryBibleState):
        append_story_bible_revision(
            initial_aggregate(),
            **arguments,  # type: ignore[arg-type]
        )


def test_append_rejects_naive_time_and_clock_rollback() -> None:
    aggregate = initial_aggregate()
    common = {
        "expected_version": ConcurrencyVersion(1),
        "revision_id": revision_id(4),
        "title": StoryBibleTitle("设定"),
        "content": StoryBibleContent(),
    }

    with pytest.raises(InvalidStoryBibleState):
        append_story_bible_revision(
            aggregate,
            now=BASE_TIME.replace(tzinfo=None),
            **common,
        )
    with pytest.raises(InvalidStoryBibleState):
        append_story_bible_revision(
            aggregate,
            now=BASE_TIME - timedelta(microseconds=1),
            **common,
        )


def test_append_rejects_reusing_current_revision_id() -> None:
    aggregate = initial_aggregate()

    with pytest.raises(InvalidStoryBibleState):
        append_story_bible_revision(
            aggregate,
            expected_version=ConcurrencyVersion(1),
            revision_id=aggregate.current_revision.id,
            title=StoryBibleTitle("设定"),
            content=StoryBibleContent(),
            now=BASE_TIME,
        )


def test_one_hundred_revision_sequence_is_deterministic_and_strictly_ordered() -> None:
    aggregate = initial_aggregate()
    all_aggregates = [aggregate]
    all_revision_ids = {aggregate.current_revision.id}

    for number in range(2, 101):
        previous = aggregate
        previous_snapshot = (
            previous.story_bible,
            previous.head,
            previous.current_revision,
        )
        next_revision_id = revision_id(number + 2)
        aggregate = append_story_bible_revision(
            previous,
            expected_version=ConcurrencyVersion(number - 1),
            revision_id=next_revision_id,
            title=StoryBibleTitle(f"设定{number}"),
            content=StoryBibleContent(f"正文{number}"),
            now=BASE_TIME + timedelta(seconds=number - 1),
        )
        assert (
            previous.story_bible,
            previous.head,
            previous.current_revision,
        ) == previous_snapshot
        assert aggregate.current_revision.revision_number == RevisionNumber(number)
        assert aggregate.story_bible.concurrency_version == ConcurrencyVersion(number)
        assert aggregate.story_bible.id == all_aggregates[0].story_bible.id
        assert aggregate.story_bible.project_id == all_aggregates[0].story_bible.project_id
        assert aggregate.head.revision_id == next_revision_id
        assert aggregate.current_revision.created_at >= previous.current_revision.created_at
        assert next_revision_id not in all_revision_ids
        all_revision_ids.add(next_revision_id)
        all_aggregates.append(aggregate)

    assert [item.current_revision.revision_number.value for item in all_aggregates] == list(
        range(1, 101)
    )
    assert [item.story_bible.concurrency_version.value for item in all_aggregates] == list(
        range(1, 101)
    )
    assert len(all_revision_ids) == 100
