"""Stable Character composite-keyset traversal."""

from datetime import timedelta
from pathlib import Path

import pytest
from tests.backend.character_repository_support import (
    BASE_TIME,
    CharacterRepositoryDatabase,
    character_aggregate,
    character_id,
    create_project,
    project_id,
    repository_database,
)

from aiwebnovel.character.persistence.list_reader import SqlAlchemyCharacterListReader

pytestmark = pytest.mark.integration


def seed_characters(
    database: CharacterRepositoryDatabase,
    values: range,
    *,
    created_at=BASE_TIME,  # type: ignore[no-untyped-def]
) -> None:
    for value in values:
        database.repository.create(
            character_aggregate(
                value,
                project_value=1,
                created_at=created_at,
                name=f"Character {value}",
            )
        )


def test_twenty_three_equal_timestamp_characters_have_no_duplicates_or_omissions(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        seed_characters(database, range(1, 24))
        reader = SqlAlchemyCharacterListReader(database.session_factory)
        first = reader.list_for_project(project_id(1), limit=20, after=None)
        assert first.next_position is not None
        second = reader.list_for_project(
            project_id(1),
            limit=20,
            after=first.next_position,
        )

    observed = [item.character_id for item in (*first.items, *second.items)]
    expected = [str(character_id(value)) for value in range(23, 0, -1)]
    assert len(first.items) == 20
    assert len(second.items) == 3
    assert first.has_more is True
    assert second.has_more is False
    assert second.next_position is None
    assert observed == expected
    assert len(observed) == len(set(observed)) == 23


def test_newer_character_is_excluded_from_old_position_and_leads_fresh_page(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        seed_characters(database, range(1, 6))
        reader = SqlAlchemyCharacterListReader(database.session_factory)
        first = reader.list_for_project(project_id(1), limit=2, after=None)
        assert first.next_position is not None
        database.repository.create(
            character_aggregate(
                6,
                project_value=1,
                created_at=BASE_TIME + timedelta(seconds=30),
            )
        )
        remaining: list[str] = []
        after = first.next_position
        while True:
            page = reader.list_for_project(project_id(1), limit=2, after=after)
            remaining.extend(item.character_id for item in page.items)
            if not page.has_more:
                break
            assert page.next_position is not None
            after = page.next_position
        fresh = reader.list_for_project(project_id(1), limit=2, after=None)

    assert str(character_id(6)) not in remaining
    assert remaining == [
        str(character_id(3)),
        str(character_id(2)),
        str(character_id(1)),
    ]
    assert fresh.items[0].character_id == str(character_id(6))
