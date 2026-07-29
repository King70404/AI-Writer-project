"""Consistent current Character aggregate read tests."""

from datetime import UTC
from pathlib import Path

import pytest
from sqlalchemy import event
from tests.backend.character_repository_support import (
    character_aggregate,
    character_id,
    character_revision_id,
    create_project,
    later,
    repository_database,
    table_state,
)

from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion

pytestmark = pytest.mark.integration


def test_get_missing_returns_none_without_writes(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        assert database.repository.get(character_id(404)) is None
        assert table_state(database.engine)["characters"] == 0


def test_get_restores_current_aggregate_with_one_select(tmp_path: Path) -> None:
    initial = character_aggregate()
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        appended = database.repository.append_revision(
            initial.character.id,
            expected_version=ConcurrencyVersion(1),
            name=CharacterName("Second"),
            role=CharacterRole("Rival"),
            profile=CharacterProfile("Current only"),
            clock=lambda: later(),
            revision_id_factory=lambda: character_revision_id(30_002),
        )

        def capture(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(database.engine, "before_cursor_execute", capture)
        try:
            loaded = database.repository.get(initial.character.id)
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)
        state = table_state(database.engine)

    assert loaded == appended
    assert loaded is not None
    assert loaded.character.created_at.tzinfo is UTC
    assert (
        len(
            [
                statement
                for statement in statements
                if statement.lstrip().upper().startswith("SELECT")
            ]
        )
        == 1
    )
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for statement in statements
    )
    assert state["character_revisions"] == 2


def test_loaded_aggregate_survives_repository_session_close(tmp_path: Path) -> None:
    initial = character_aggregate(profile="detached")
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        loaded = database.repository.get(initial.character.id)

    assert loaded == initial
    assert loaded is not None
    assert str(loaded.current_revision.profile) == "detached"
