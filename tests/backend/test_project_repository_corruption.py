"""Stored Project corruption detection tests."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest
from tests.backend.project_repository_support import project_id, repository_database, revision_id

from aiwebnovel.project.errors import ProjectDataCorruption

pytestmark = pytest.mark.integration

_NOW = "2026-04-05 06:07:08.000000"
_LATER = "2026-04-05 06:07:09.000000"
_EARLIER = "2026-04-05 06:07:07.000000"


def _project(
    connection: sqlite3.Connection,
    identifier: int,
    *,
    version: int = 1,
    created_at: str = _NOW,
    updated_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO projects (id, concurrency_version, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        (str(project_id(identifier)), version, created_at, updated_at),
    )


def _revision(
    connection: sqlite3.Connection,
    identifier: int,
    owner: int,
    *,
    title: str = "Valid",
    created_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO project_revisions "
        "(id, project_id, revision_number, title, description, created_at) "
        "VALUES (?, ?, 1, ?, '', ?)",
        (str(revision_id(identifier)), str(project_id(owner)), title, created_at),
    )


def _head(
    connection: sqlite3.Connection,
    owner: int,
    revision: int,
    *,
    updated_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO project_heads (project_id, revision_id, updated_at) VALUES (?, ?, ?)",
        (str(project_id(owner)), str(revision_id(revision)), updated_at),
    )


def _missing_head(connection: sqlite3.Connection) -> None:
    _project(connection, 1)


def _missing_revision(connection: sqlite3.Connection) -> None:
    _project(connection, 1)
    _head(connection, 1, 11)


def _ownership_mismatch(connection: sqlite3.Connection) -> None:
    _project(connection, 1)
    _project(connection, 2)
    _revision(connection, 12, 2)
    _head(connection, 1, 12)


def _invalid_project_value(connection: sqlite3.Connection) -> None:
    _project(connection, 1, version=0)
    _revision(connection, 11, 1)
    _head(connection, 1, 11)


def _invalid_revision_value(connection: sqlite3.Connection) -> None:
    _project(connection, 1)
    _revision(connection, 11, 1, title="\x01")
    _head(connection, 1, 11)


def _head_before_revision(connection: sqlite3.Connection) -> None:
    _project(connection, 1, updated_at=_LATER)
    _revision(connection, 11, 1, created_at=_LATER)
    _head(connection, 1, 11, updated_at=_EARLIER)


def _project_updated_before_created(connection: sqlite3.Connection) -> None:
    _project(connection, 1, created_at=_LATER, updated_at=_EARLIER)
    _revision(connection, 11, 1, created_at=_LATER)
    _head(connection, 1, 11, updated_at=_LATER)


@pytest.mark.parametrize(
    "corrupt",
    [
        _missing_head,
        _missing_revision,
        _ownership_mismatch,
        _invalid_project_value,
        _invalid_revision_value,
        _head_before_revision,
        _project_updated_before_created,
    ],
    ids=(
        "project-without-head",
        "head-without-revision",
        "revision-owner-mismatch",
        "invalid-project-domain-value",
        "invalid-revision-domain-value",
        "head-time-before-revision",
        "project-updated-before-created",
    ),
)
def test_get_rejects_inconsistent_stored_aggregate(
    tmp_path: Path,
    corrupt: Callable[[sqlite3.Connection], None],
) -> None:
    with repository_database(tmp_path) as database:
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            corrupt(connection)
            connection.commit()

        with pytest.raises(ProjectDataCorruption) as captured:
            database.repository.get(project_id(1))

        assert str(captured.value) == "The stored Project state is inconsistent."
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM projects").scalar_one() >= 1
