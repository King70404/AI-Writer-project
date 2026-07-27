"""Immutable primitive query contracts for current Story Bible reads."""

from dataclasses import FrozenInstanceError, fields

import pytest

from aiwebnovel.story_bible.application.queries import (
    GetStoryBibleForProjectQuery,
    GetStoryBibleQuery,
)


@pytest.mark.parametrize(
    ("query", "field_name"),
    [
        (GetStoryBibleQuery("story-bible"), "story_bible_id"),
        (GetStoryBibleForProjectQuery("project"), "project_id"),
    ],
)
def test_query_has_one_primitive_field_and_is_frozen(
    query: GetStoryBibleQuery | GetStoryBibleForProjectQuery,
    field_name: str,
) -> None:
    assert tuple(field.name for field in fields(query)) == (field_name,)
    assert type(getattr(query, field_name)) is str
    assert not hasattr(query, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(query, field_name, "changed")


def test_query_construction_does_not_validate_or_add_hidden_behavior() -> None:
    by_id = GetStoryBibleQuery(object())  # type: ignore[arg-type]
    by_project = GetStoryBibleForProjectQuery(object())  # type: ignore[arg-type]
    forbidden = {"history", "include_history", "limit", "page", "repository", "session"}

    assert type(by_id.story_bible_id) is object
    assert type(by_project.project_id) is object
    assert forbidden.isdisjoint(field.name for field in fields(by_id))
    assert forbidden.isdisjoint(field.name for field in fields(by_project))
