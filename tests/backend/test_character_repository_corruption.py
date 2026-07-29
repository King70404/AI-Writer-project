"""Stored Character corruption detection tests."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest
from tests.backend.character_repository_support import (
    character_id,
    character_revision_id,
    create_project,
    project_id,
    repository_database,
)

from aiwebnovel.character.errors import CharacterDataCorruption

pytestmark = pytest.mark.integration

_NOW = "2026-07-29 08:09:10.000000"
_LATER = "2026-07-29 08:09:11.000000"
_EARLIER = "2026-07-29 08:09:09.000000"


def _stable(
    connection: sqlite3.Connection,
    identifier: int,
    *,
    project: int = 1,
    version: int = 1,
    created_at: str = _NOW,
    updated_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO characters "
        "(id, project_id, concurrency_version, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            str(character_id(identifier)),
            str(project_id(project)),
            version,
            created_at,
            updated_at,
        ),
    )


def _revision(
    connection: sqlite3.Connection,
    identifier: int,
    owner: int,
    *,
    number: int = 1,
    name: str = "Valid",
    role: str = "",
    profile: str = "",
    created_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO character_revisions "
        "(id, character_id, revision_number, name, role, profile, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(character_revision_id(identifier)),
            str(character_id(owner)),
            number,
            name,
            role,
            profile,
            created_at,
        ),
    )


def _head(
    connection: sqlite3.Connection,
    owner: int,
    revision: int,
    *,
    updated_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO character_heads (character_id, revision_id, updated_at) VALUES (?, ?, ?)",
        (
            str(character_id(owner)),
            str(character_revision_id(revision)),
            updated_at,
        ),
    )


def _missing_project(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, project=99)
    _revision(connection, 11, 1)
    _head(connection, 1, 11)


def _missing_head(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)


def _missing_revision(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    _head(connection, 1, 11)


def _ownership_mismatch(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    _stable(connection, 2, project=2)
    _revision(connection, 12, 2)
    _head(connection, 1, 12)


def _invalid_stable_value(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, version=0)
    _revision(connection, 11, 1)
    _head(connection, 1, 11)


def _invalid_name(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    _revision(connection, 11, 1, name="")
    _head(connection, 1, 11)


def _invalid_role(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    _revision(connection, 11, 1, role="x" * 121)
    _head(connection, 1, 11)


def _invalid_profile(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    _revision(connection, 11, 1, profile="x" * 50_001)
    _head(connection, 1, 11)


def _invalid_revision_number(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    _revision(connection, 11, 1, number=0)
    _head(connection, 1, 11)


def _invalid_project_identifier(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO characters "
        "(id, project_id, concurrency_version, created_at, updated_at) "
        "VALUES (?, 'invalid-project-id', 1, ?, ?)",
        (str(character_id(1)), _NOW, _NOW),
    )
    _revision(connection, 11, 1)
    _head(connection, 1, 11)


def _invalid_revision_identifier(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    connection.execute(
        "INSERT INTO character_revisions "
        "(id, character_id, revision_number, name, role, profile, created_at) "
        "VALUES ('invalid-revision-id', ?, 1, 'Valid', '', '', ?)",
        (str(character_id(1)), _NOW),
    )
    connection.execute(
        "INSERT INTO character_heads (character_id, revision_id, updated_at) "
        "VALUES (?, 'invalid-revision-id', ?)",
        (str(character_id(1)), _NOW),
    )


def _invalid_time(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, created_at="not-a-time", updated_at="not-a-time")
    _revision(connection, 11, 1)
    _head(connection, 1, 11)


def _stable_updated_before_created(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, created_at=_LATER, updated_at=_EARLIER)
    _revision(connection, 11, 1, created_at=_EARLIER)
    _head(connection, 1, 11, updated_at=_EARLIER)


def _version_revision_mismatch(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, version=2)
    _revision(connection, 11, 1)
    _head(connection, 1, 11)


def _stable_head_time_mismatch(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, updated_at=_LATER)
    _revision(connection, 11, 1, created_at=_LATER)
    _head(connection, 1, 11, updated_at=_NOW)


def _stable_revision_time_mismatch(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, updated_at=_LATER)
    _revision(connection, 11, 1, created_at=_NOW)
    _head(connection, 1, 11, updated_at=_LATER)


def _revision_before_stable_created(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    _revision(connection, 11, 1, created_at=_EARLIER)
    _head(connection, 1, 11)


@pytest.mark.parametrize(
    "corrupt",
    [
        _missing_project,
        _missing_head,
        _missing_revision,
        _ownership_mismatch,
        _invalid_stable_value,
        _invalid_name,
        _invalid_role,
        _invalid_profile,
        _invalid_revision_number,
        _invalid_project_identifier,
        _invalid_revision_identifier,
        _invalid_time,
        _stable_updated_before_created,
        _version_revision_mismatch,
        _stable_head_time_mismatch,
        _stable_revision_time_mismatch,
        _revision_before_stable_created,
    ],
)
def test_get_rejects_inconsistent_stored_aggregate_without_private_data(
    tmp_path: Path,
    corrupt: Callable[[sqlite3.Connection], None],
) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        create_project(database, 2)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            corrupt(connection)
            connection.commit()

        with pytest.raises(CharacterDataCorruption) as captured:
            database.repository.get(character_id(1))

    assert str(captured.value) == "The stored Character state is inconsistent."
    assert "Valid" not in str(captured.value)


def test_explicit_head_not_highest_revision_is_authoritative(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            _stable(connection, 1)
            _revision(connection, 11, 1, number=1, name="Head")
            _revision(connection, 12, 1, number=2, name="Unpointed", created_at=_LATER)
            _head(connection, 1, 11)
            connection.commit()
        restored = database.repository.get(character_id(1))

    assert restored is not None
    assert str(restored.current_revision.name) == "Head"
    assert restored.current_revision.revision_number.value == 1


def test_corruption_isolated_between_characters(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            _stable(connection, 1)
            _revision(connection, 11, 1)
            _head(connection, 1, 11)
            _stable(connection, 2, version=0)
            _revision(connection, 12, 2)
            _head(connection, 2, 12)
            connection.commit()
        valid = database.repository.get(character_id(1))
        with pytest.raises(CharacterDataCorruption):
            database.repository.get(character_id(2))

    assert valid is not None
    assert valid.character.id == character_id(1)
