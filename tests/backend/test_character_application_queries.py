"""Character application query and Position contracts."""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime

import pytest
from tests.backend.character_repository_support import (
    BASE_TIME,
    character_id,
    project_id,
)

from aiwebnovel.character.application.models import CharacterListPosition
from aiwebnovel.character.application.queries import (
    GetCharacterQuery,
    ListCharactersForProjectQuery,
    validate_character_list_limit,
)


def test_get_query_is_frozen_and_has_only_character_id() -> None:
    query = GetCharacterQuery("character")

    assert tuple(field.name for field in fields(query)) == ("character_id",)
    with pytest.raises(FrozenInstanceError):
        query.character_id = "changed"  # type: ignore[misc]


def test_list_query_defaults_and_exact_fields() -> None:
    query = ListCharactersForProjectQuery("project")

    assert tuple(field.name for field in fields(query)) == (
        "project_id",
        "limit",
        "after",
    )
    assert query.limit == 20
    assert query.after is None
    with pytest.raises(FrozenInstanceError):
        query.limit = 10  # type: ignore[misc]


@pytest.mark.parametrize("limit", [1, 20, 100])
def test_list_limit_accepts_exact_integer_bounds(limit: int) -> None:
    assert validate_character_list_limit(limit) == limit
    assert ListCharactersForProjectQuery("project", limit).limit == limit


@pytest.mark.parametrize("limit", [True, False, 0, -1, 101, 1.0, "20", None])
def test_list_limit_rejects_coercible_or_out_of_range_values(limit: object) -> None:
    with pytest.raises(ValueError):
        validate_character_list_limit(limit)
    with pytest.raises(ValueError):
        ListCharactersForProjectQuery("project", limit)  # type: ignore[arg-type]


def test_position_requires_exact_ids_aware_utc_and_is_frozen() -> None:
    position = CharacterListPosition(project_id(1), BASE_TIME, character_id(1))

    assert tuple(field.name for field in fields(position)) == (
        "project_id",
        "created_at",
        "character_id",
    )
    assert position.created_at.tzinfo is not None
    with pytest.raises(FrozenInstanceError):
        position.created_at = BASE_TIME  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"project_id": "bad"}, TypeError),
        ({"character_id": "bad"}, TypeError),
        ({"created_at": "bad"}, TypeError),
        ({"created_at": datetime(2026, 1, 1)}, ValueError),
    ],
)
def test_position_rejects_invalid_types_and_naive_time(
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    values: dict[str, object] = {
        "project_id": project_id(1),
        "created_at": BASE_TIME,
        "character_id": character_id(1),
    }
    values.update(changes)
    with pytest.raises(error):
        CharacterListPosition(**values)  # type: ignore[arg-type]


def test_list_query_requires_exact_position_type() -> None:
    with pytest.raises(TypeError):
        ListCharactersForProjectQuery("project", after=object())  # type: ignore[arg-type]
