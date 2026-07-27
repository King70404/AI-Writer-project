"""Strict detached StoryBibleSnapshot validation."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone

import pytest
from tests.backend.story_bible_support import (
    BASE_TIME,
    project_id,
    revision_id,
    story_bible_id,
)

from aiwebnovel.domain.errors import (
    InvalidConcurrencyVersion,
    InvalidDomainIdentifier,
    InvalidRevisionNumber,
)
from aiwebnovel.story_bible.application.models import StoryBibleSnapshot
from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleContent,
    InvalidStoryBibleTitle,
)

CANARY = "STORY_BIBLE_APPLICATION_SECRET_CANARY"


def snapshot_values() -> dict[str, object]:
    return {
        "story_bible_id": str(story_bible_id()),
        "project_id": str(project_id()),
        "current_revision_id": str(revision_id()),
        "revision_number": 1,
        "concurrency_version": 1,
        "title": "  设定集  ",
        "content": "line one\r\nline two\r",
        "created_at": BASE_TIME,
        "updated_at": BASE_TIME,
        "revision_created_at": BASE_TIME,
        "head_updated_at": BASE_TIME,
    }


def make_snapshot(**changes: object) -> StoryBibleSnapshot:
    values = snapshot_values()
    values.update(changes)
    return StoryBibleSnapshot(**values)  # type: ignore[arg-type]


def test_snapshot_has_exact_detached_fields_normalizes_values_and_is_frozen() -> None:
    non_utc = BASE_TIME.astimezone(timezone(timedelta(hours=8)))
    snapshot = make_snapshot(
        created_at=non_utc,
        updated_at=non_utc,
        revision_created_at=non_utc,
        head_updated_at=non_utc,
    )

    assert tuple(field.name for field in fields(snapshot)) == (
        "story_bible_id",
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "content",
        "created_at",
        "updated_at",
        "revision_created_at",
        "head_updated_at",
    )
    assert snapshot.title == "设定集"
    assert snapshot.content == "line one\nline two\n"
    assert snapshot.created_at.tzinfo is UTC
    assert all(
        type(value) in {str, int, datetime}
        for value in (
            snapshot.story_bible_id,
            snapshot.project_id,
            snapshot.current_revision_id,
            snapshot.revision_number,
            snapshot.concurrency_version,
            snapshot.title,
            snapshot.content,
            snapshot.created_at,
            snapshot.updated_at,
            snapshot.revision_created_at,
            snapshot.head_updated_at,
        )
    )
    assert not hasattr(snapshot, "__dict__")
    with pytest.raises(FrozenInstanceError):
        snapshot.title = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "error_type"),
    [
        ({"story_bible_id": 1}, TypeError),
        ({"story_bible_id": "invalid"}, InvalidDomainIdentifier),
        ({"project_id": 1}, TypeError),
        ({"project_id": str(project_id(31)).lower()}, ValueError),
        ({"current_revision_id": 1}, TypeError),
        ({"current_revision_id": "invalid"}, InvalidDomainIdentifier),
        ({"revision_number": True}, TypeError),
        ({"revision_number": 0}, InvalidRevisionNumber),
        ({"concurrency_version": True}, TypeError),
        ({"concurrency_version": 0}, InvalidConcurrencyVersion),
        ({"revision_number": 2}, ValueError),
        ({"title": 1}, TypeError),
        ({"title": " "}, InvalidStoryBibleTitle),
        ({"content": 1}, TypeError),
        ({"content": "\x00"}, InvalidStoryBibleContent),
        ({"created_at": "time"}, TypeError),
        ({"created_at": datetime(2026, 1, 1)}, ValueError),
        ({"created_at": BASE_TIME + timedelta(seconds=1)}, ValueError),
        ({"revision_created_at": BASE_TIME + timedelta(seconds=1)}, ValueError),
        ({"head_updated_at": BASE_TIME + timedelta(seconds=1)}, ValueError),
    ],
)
def test_snapshot_rejects_each_invalid_primitive_or_invariant(
    changes: dict[str, object],
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        make_snapshot(**changes)


def test_snapshot_errors_do_not_echo_title_or_content() -> None:
    for changes in (
        {"title": f"\x00{CANARY}"},
        {"content": f"\x00{CANARY}"},
    ):
        with pytest.raises(Exception) as captured:
            make_snapshot(**changes)
        assert CANARY not in str(captured.value)
