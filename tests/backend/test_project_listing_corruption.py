"""Whole-page failure for corrupted Project list storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest
from tests.backend.project_repository_support import project_id, repository_database, revision_id

from aiwebnovel.project.errors import ProjectDataCorruption
from aiwebnovel.project.persistence.listing import SqlAlchemyProjectListReader

pytestmark = pytest.mark.integration

_NOW = "2026-06-01 02:03:04.000000"
_LATER = "2026-06-01 02:03:05.000000"
_EARLIER = "2026-06-01 02:03:03.000000"


def _project(
    connection: sqlite3.Connection,
    identifier: str,
    *,
    version: object = 1,
    created_at: str = _NOW,
    updated_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO projects (id, concurrency_version, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (identifier, version, created_at, updated_at),
    )


def _revision(
    connection: sqlite3.Connection,
    identifier: str,
    owner: str,
    *,
    number: object = 1,
    title: str = "Valid",
    created_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO project_revisions "
        "(id, project_id, revision_number, title, description, created_at) "
        "VALUES (?, ?, ?, ?, '', ?)",
        (identifier, owner, number, title, created_at),
    )


def _head(
    connection: sqlite3.Connection,
    owner: str,
    revision: str,
    *,
    updated_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO project_heads (project_id, revision_id, updated_at) VALUES (?, ?, ?)",
        (owner, revision, updated_at),
    )


def _valid(connection: sqlite3.Connection, value: int = 1) -> tuple[str, str]:
    owner = str(project_id(value))
    revision = str(revision_id(value + 100))
    _project(connection, owner)
    _revision(connection, revision, owner)
    _head(connection, owner, revision)
    return owner, revision


def missing_head(connection: sqlite3.Connection) -> None:
    _project(connection, str(project_id(1)))


def missing_revision(connection: sqlite3.Connection) -> None:
    owner = str(project_id(1))
    _project(connection, owner)
    _head(connection, owner, str(revision_id(101)))


def ownership_mismatch(connection: sqlite3.Connection) -> None:
    first = str(project_id(1))
    second = str(project_id(2))
    revision = str(revision_id(101))
    _project(connection, first)
    _project(connection, second)
    _revision(connection, revision, second)
    _head(connection, first, revision)


def invalid_project_id(connection: sqlite3.Connection) -> None:
    revision = str(revision_id(101))
    _project(connection, "CANARY_INVALID_PROJECT")
    _revision(connection, revision, "CANARY_INVALID_PROJECT")
    _head(connection, "CANARY_INVALID_PROJECT", revision)


def invalid_revision_id(connection: sqlite3.Connection) -> None:
    owner = str(project_id(1))
    _project(connection, owner)
    _revision(connection, "CANARY_INVALID_REVISION", owner)
    _head(connection, owner, "CANARY_INVALID_REVISION")


def invalid_revision_number(connection: sqlite3.Connection) -> None:
    owner, revision = str(project_id(1)), str(revision_id(101))
    _project(connection, owner)
    _revision(connection, revision, owner, number=0)
    _head(connection, owner, revision)


def invalid_concurrency_version(connection: sqlite3.Connection) -> None:
    owner, revision = str(project_id(1)), str(revision_id(101))
    _project(connection, owner, version=0)
    _revision(connection, revision, owner)
    _head(connection, owner, revision)


def invalid_time(connection: sqlite3.Connection) -> None:
    owner, revision = str(project_id(1)), str(revision_id(101))
    _project(connection, owner, created_at="CANARY_INVALID_TIME")
    _revision(connection, revision, owner)
    _head(connection, owner, revision)


def invalid_time_order(connection: sqlite3.Connection) -> None:
    owner, revision = str(project_id(1)), str(revision_id(101))
    _project(connection, owner, created_at=_LATER, updated_at=_EARLIER)
    _revision(connection, revision, owner, created_at=_LATER)
    _head(connection, owner, revision, updated_at=_EARLIER)


def invalid_title(connection: sqlite3.Connection) -> None:
    owner, revision = str(project_id(1)), str(revision_id(101))
    _project(connection, owner)
    _revision(connection, revision, owner, title="CANARY\x01")
    _head(connection, owner, revision)


def noncanonical_title(connection: sqlite3.Connection) -> None:
    owner, revision = str(project_id(1)), str(revision_id(101))
    _project(connection, owner)
    _revision(connection, revision, owner, title=" Padded title ")
    _head(connection, owner, revision)


@pytest.mark.parametrize(
    "corrupt",
    [
        missing_head,
        missing_revision,
        ownership_mismatch,
        invalid_project_id,
        invalid_revision_id,
        invalid_revision_number,
        invalid_concurrency_version,
        invalid_time,
        invalid_time_order,
        invalid_title,
        noncanonical_title,
    ],
)
def test_corruption_fails_the_whole_page_without_changes_or_canary_leak(
    tmp_path: Path,
    corrupt: Callable[[sqlite3.Connection], None],
) -> None:
    with repository_database(tmp_path) as database:
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            _valid(connection, 9)
            corrupt(connection)
            connection.commit()
            before = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]

        with pytest.raises(ProjectDataCorruption) as captured:
            SqlAlchemyProjectListReader(database.session_factory).list_page(
                limit=100,
                after=None,
            )

        assert str(captured.value) == "The stored Project state is inconsistent."
        assert "CANARY" not in str(captured.value)
        with database.engine.connect() as connection:
            after = connection.exec_driver_sql("SELECT COUNT(*) FROM projects").scalar_one()
        assert after == before
