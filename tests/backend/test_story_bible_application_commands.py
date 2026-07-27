"""Immutable primitive command contracts for Story Bible application writes."""

from dataclasses import FrozenInstanceError, fields

import pytest

from aiwebnovel.story_bible.application.commands import (
    CreateStoryBibleCommand,
    ReviseStoryBibleCommand,
)


def test_create_command_has_exact_primitive_fields_and_is_frozen() -> None:
    command = CreateStoryBibleCommand(
        project_id="project",
        title="title",
        content="content",
    )

    assert tuple(field.name for field in fields(command)) == (
        "project_id",
        "title",
        "content",
    )
    assert tuple(type(getattr(command, field.name)) for field in fields(command)) == (
        str,
        str,
        str,
    )
    assert not hasattr(command, "__dict__")
    with pytest.raises(FrozenInstanceError):
        command.title = "changed"  # type: ignore[misc]


def test_revise_command_has_exact_primitive_fields_and_is_frozen() -> None:
    command = ReviseStoryBibleCommand(
        story_bible_id="story-bible",
        expected_version=1,
        title="title",
        content="content",
    )

    assert tuple(field.name for field in fields(command)) == (
        "story_bible_id",
        "expected_version",
        "title",
        "content",
    )
    assert tuple(type(getattr(command, field.name)) for field in fields(command)) == (
        str,
        int,
        str,
        str,
    )
    assert not hasattr(command, "__dict__")
    with pytest.raises(FrozenInstanceError):
        command.expected_version = 2  # type: ignore[misc]


def test_command_construction_has_no_conversion_or_side_effect_fields() -> None:
    create = CreateStoryBibleCommand(object(), object(), object())  # type: ignore[arg-type]
    revise = ReviseStoryBibleCommand(object(), True, object(), object())  # type: ignore[arg-type]

    assert type(create.project_id) is object
    assert type(revise.expected_version) is bool
    forbidden = {
        "clock",
        "repository",
        "session",
        "story_bible_id_factory",
        "revision_id_factory",
        "revision_id",
        "revision_number",
        "concurrency_version",
    }
    assert forbidden.isdisjoint(field.name for field in fields(create))
    assert forbidden.isdisjoint(field.name for field in fields(revise))
