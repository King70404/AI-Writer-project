"""Real SQLite Character list-reader semantics and SQL bounds."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError, StatementError
from tests.backend.character_repository_support import (
    BASE_TIME,
    character_aggregate,
    character_id,
    character_revision_id,
    create_project,
    project_id,
    repository_database,
)

from aiwebnovel.character.application.models import CharacterListPosition
from aiwebnovel.character.errors import (
    CharacterDataCorruption,
    CharacterProjectNotFound,
    CharacterRepositoryError,
    InvalidCharacterName,
    InvalidCharacterState,
)
from aiwebnovel.character.persistence.list_reader import (
    SqlAlchemyCharacterListReader,
    _list_item_from_row,
    character_list_statement,
)
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber

pytestmark = pytest.mark.integration


def test_missing_project_is_distinct_from_existing_project_empty_page(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        reader = SqlAlchemyCharacterListReader(database.session_factory)
        with pytest.raises(CharacterProjectNotFound) as captured:
            reader.list_for_project(project_id(404), limit=20, after=None)
        create_project(database)
        empty = reader.list_for_project(project_id(1), limit=20, after=None)

    assert captured.value.project_id == project_id(404)
    assert empty.project_id == str(project_id(1))
    assert empty.items == ()
    assert empty.has_more is False
    assert empty.next_position is None


def test_lists_same_name_characters_for_only_requested_project_without_profile(
    tmp_path: Path,
) -> None:
    privacy_canary = "CHARACTER_APPLICATION_SECRET_CANARY"
    with repository_database(tmp_path) as database:
        create_project(database, 1)
        create_project(database, 2)
        database.repository.create(
            character_aggregate(
                1,
                project_value=1,
                name="Shared Name",
                role="Hero",
                profile=privacy_canary,
            )
        )
        database.repository.create(
            character_aggregate(
                2,
                project_value=1,
                name="Shared Name",
                role="Rival",
                profile=privacy_canary,
            )
        )
        database.repository.create(character_aggregate(3, project_value=2))
        page = SqlAlchemyCharacterListReader(database.session_factory).list_for_project(
            project_id(1), limit=20, after=None
        )

    assert [item.character_id for item in page.items] == [
        str(character_id(2)),
        str(character_id(1)),
    ]
    assert [item.name for item in page.items] == ["Shared Name", "Shared Name"]
    assert [item.role for item in page.items] == ["Rival", "Hero"]
    assert all(not hasattr(item, "profile") for item in page.items)
    assert privacy_canary not in repr(page)
    assert str(character_id(3)) not in {item.character_id for item in page.items}


def test_limit_plus_one_and_fixed_keyset_order(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        for value in range(1, 4):
            database.repository.create(
                character_aggregate(
                    value,
                    project_value=1,
                    created_at=BASE_TIME + timedelta(seconds=value),
                )
            )
        page = SqlAlchemyCharacterListReader(database.session_factory).list_for_project(
            project_id(1), limit=2, after=None
        )

    assert [item.character_id for item in page.items] == [
        str(character_id(3)),
        str(character_id(2)),
    ]
    assert page.has_more is True
    assert page.next_position == CharacterListPosition(
        project_id(1),
        BASE_TIME + timedelta(seconds=2),
        character_id(2),
    )
    assert str(character_id(1)) not in {item.character_id for item in page.items}


def test_normal_list_path_uses_two_selects_without_count_offset_or_profile(
    tmp_path: Path,
) -> None:
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(character_aggregate(1))

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
            SqlAlchemyCharacterListReader(database.session_factory).list_for_project(
                project_id(1), limit=20, after=None
            )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)

    selects = [
        statement for statement in statements if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) == 2
    list_sql = selects[1].upper()
    assert "LEFT OUTER JOIN CHARACTER_HEADS" in list_sql
    assert "LEFT OUTER JOIN CHARACTER_REVISIONS" in list_sql
    assert "COUNT(" not in list_sql
    assert " OFFSET " not in list_sql
    assert "PROFILE" not in list_sql
    assert "ORDER BY CHARACTERS.CREATED_AT DESC, CHARACTERS.ID DESC" in list_sql
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for statement in statements
    )


def test_keyset_statement_uses_strict_descending_composite_bound() -> None:
    statement = character_list_statement(
        project_id(1),
        limit=20,
        after=CharacterListPosition(project_id(1), BASE_TIME, character_id(5)),
    )
    sql = str(statement).upper()
    assert "CHARACTERS.CREATED_AT <" in sql
    assert "CHARACTERS.CREATED_AT =" in sql
    assert "CHARACTERS.ID <" in sql
    assert "<=" not in sql
    assert "OFFSET" not in sql
    assert "PROFILE" not in sql


def test_head_is_authoritative_instead_of_highest_revision(tmp_path: Path) -> None:
    now = "2026-07-29 08:09:10.000000"
    later = "2026-07-29 08:09:11.000000"
    with repository_database(tmp_path) as database:
        create_project(database)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            connection.execute(
                "INSERT INTO characters "
                "(id, project_id, concurrency_version, created_at, updated_at) "
                "VALUES (?, ?, 1, ?, ?)",
                (str(character_id(1)), str(project_id(1)), now, now),
            )
            connection.execute(
                "INSERT INTO character_revisions "
                "(id, character_id, revision_number, name, role, profile, created_at) "
                "VALUES (?, ?, 1, 'Head Name', 'Head Role', '', ?)",
                (str(character_revision_id(31)), str(character_id(1)), now),
            )
            connection.execute(
                "INSERT INTO character_revisions "
                "(id, character_id, revision_number, name, role, profile, created_at) "
                "VALUES (?, ?, 2, 'Unpointed', 'Later', '', ?)",
                (str(character_revision_id(32)), str(character_id(1)), later),
            )
            connection.execute(
                "INSERT INTO character_heads (character_id, revision_id, updated_at) "
                "VALUES (?, ?, ?)",
                (str(character_id(1)), str(character_revision_id(31)), now),
            )
            connection.commit()
        page = SqlAlchemyCharacterListReader(database.session_factory).list_for_project(
            project_id(1), limit=20, after=None
        )

    assert len(page.items) == 1
    assert page.items[0].name == "Head Name"
    assert page.items[0].current_revision_id == str(character_revision_id(31))
    assert page.items[0].revision_number == 1


def test_one_corrupt_row_fails_the_whole_page_without_leaking_text(
    tmp_path: Path,
) -> None:
    privacy_canary = "CHARACTER_APPLICATION_SECRET_CANARY"
    with repository_database(tmp_path) as database:
        create_project(database)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(
                "INSERT INTO characters "
                "(id, project_id, concurrency_version, created_at, updated_at) "
                "VALUES (?, ?, 2, '2026-07-29 08:09:10.000000', "
                "'2026-07-29 08:09:10.000000')",
                (str(character_id(1)), str(project_id(1))),
            )
            connection.execute(
                "INSERT INTO character_revisions "
                "(id, character_id, revision_number, name, role, profile, created_at) "
                "VALUES (?, ?, 1, ?, '', '', '2026-07-29 08:09:10.000000')",
                (str(character_revision_id(31)), str(character_id(1)), privacy_canary),
            )
            connection.execute(
                "INSERT INTO character_heads (character_id, revision_id, updated_at) "
                "VALUES (?, ?, '2026-07-29 08:09:10.000000')",
                (str(character_id(1)), str(character_revision_id(31))),
            )
            connection.commit()
        with pytest.raises(CharacterDataCorruption) as captured:
            SqlAlchemyCharacterListReader(database.session_factory).list_for_project(
                project_id(1), limit=20, after=None
            )

    assert str(captured.value) == "The stored Character state is inconsistent."
    assert privacy_canary not in str(captured.value)


def test_reader_rejects_invalid_inputs_before_opening_session() -> None:
    calls = 0

    def factory() -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("session must not be opened")

    reader = SqlAlchemyCharacterListReader(factory)  # type: ignore[arg-type]
    with pytest.raises(InvalidCharacterState):
        reader.list_for_project("bad", limit=20, after=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        reader.list_for_project(project_id(1), limit=0, after=None)
    with pytest.raises(TypeError):
        reader.list_for_project(project_id(1), limit=20, after=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        reader.list_for_project(
            project_id(1),
            limit=20,
            after=CharacterListPosition(project_id(2), BASE_TIME, character_id(1)),
        )
    assert calls == 0


def test_reader_rejects_non_callable_session_factory() -> None:
    with pytest.raises(TypeError, match="session_factory must be callable"):
        SqlAlchemyCharacterListReader(object())  # type: ignore[arg-type]


@pytest.mark.parametrize("failure", [RuntimeError("private"), sqlite3.Error("private")])
def test_session_factory_failure_is_wrapped_without_private_text(
    failure: Exception,
) -> None:
    def factory() -> object:
        raise failure

    with pytest.raises(CharacterRepositoryError) as captured:
        SqlAlchemyCharacterListReader(factory).list_for_project(  # type: ignore[arg-type]
            project_id(1),
            limit=20,
            after=None,
        )
    assert "private" not in str(captured.value)


def test_row_projection_rejects_wrong_types_and_noncanonical_text() -> None:
    with pytest.raises(CharacterDataCorruption):
        _list_item_from_row((None,) * 14, project_id=project_id(1))

    row: tuple[object, ...] = (
        character_id(1),
        project_id(1),
        ConcurrencyVersion(1),
        BASE_TIME,
        BASE_TIME,
        character_id(1),
        character_revision_id(31),
        BASE_TIME,
        character_revision_id(31),
        character_id(1),
        RevisionNumber(1),
        "  Padded Name  ",
        "Role",
        BASE_TIME,
    )
    with pytest.raises(CharacterDataCorruption):
        _list_item_from_row(row, project_id=project_id(1))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (InvalidCharacterName(), CharacterDataCorruption),
        (
            StatementError("private", "SELECT", {}, ValueError("private")),
            CharacterDataCorruption,
        ),
        (
            StatementError("private", "SELECT", {}, sqlite3.Error("private")),
            CharacterRepositoryError,
        ),
        (SQLAlchemyError("private"), CharacterRepositoryError),
        (RuntimeError("private"), CharacterRepositoryError),
    ],
)
def test_reader_maps_session_failures_and_always_rolls_back_and_closes(
    failure: Exception,
    expected: type[Exception],
) -> None:
    class FailingSession:
        def __init__(self) -> None:
            self.rolled_back = False
            self.closed = False

        def scalar(self, _statement: object) -> object:
            raise failure

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    session = FailingSession()
    reader = SqlAlchemyCharacterListReader(
        lambda: session  # type: ignore[return-value]
    )

    with pytest.raises(expected) as captured:
        reader.list_for_project(project_id(1), limit=20, after=None)

    assert session.rolled_back is True
    assert session.closed is True
    assert "private" not in str(captured.value)
