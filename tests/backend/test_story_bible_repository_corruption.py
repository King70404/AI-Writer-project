"""Stored Story Bible corruption detection tests."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy.exc import MultipleResultsFound
from tests.backend.story_bible_repository_support import (
    create_project,
    project_id,
    repository_database,
    story_bible_aggregate,
    story_bible_id,
    story_bible_revision_id,
)

from aiwebnovel.story_bible.errors import StoryBibleDataCorruption
from aiwebnovel.story_bible.persistence.mappers import story_bible_aggregate_to_records
from aiwebnovel.story_bible.persistence.repository import (
    SqlAlchemyStoryBibleRepository,
)

pytestmark = pytest.mark.integration

_NOW = "2026-06-07 08:09:10.000000"
_LATER = "2026-06-07 08:09:11.000000"
_EARLIER = "2026-06-07 08:09:09.000000"


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
        "INSERT INTO story_bibles "
        "(id, project_id, concurrency_version, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            str(story_bible_id(identifier)),
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
    title: str = "Valid",
    created_at: str = _NOW,
) -> None:
    connection.execute(
        "INSERT INTO story_bible_revisions "
        "(id, story_bible_id, revision_number, title, content, created_at) "
        "VALUES (?, ?, 1, ?, '', ?)",
        (
            str(story_bible_revision_id(identifier)),
            str(story_bible_id(owner)),
            title,
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
        "INSERT INTO story_bible_heads (story_bible_id, revision_id, updated_at) VALUES (?, ?, ?)",
        (
            str(story_bible_id(owner)),
            str(story_bible_revision_id(revision)),
            updated_at,
        ),
    )


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


def _invalid_revision_value(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    _revision(connection, 11, 1, title="")
    _head(connection, 1, 11)


def _inconsistent_times(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, created_at=_NOW, updated_at=_LATER)
    _revision(connection, 11, 1, created_at=_LATER)
    _head(connection, 1, 11, updated_at=_EARLIER)


def _invalid_project_identifier(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO story_bibles "
        "(id, project_id, concurrency_version, created_at, updated_at) "
        "VALUES (?, 'invalid-project-id', 1, ?, ?)",
        (str(story_bible_id(1)), _NOW, _NOW),
    )
    _revision(connection, 11, 1)
    _head(connection, 1, 11)


def _invalid_revision_identifier(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    connection.execute(
        "INSERT INTO story_bible_revisions "
        "(id, story_bible_id, revision_number, title, content, created_at) "
        "VALUES ('invalid-revision-id', ?, 1, 'Valid', '', ?)",
        (str(story_bible_id(1)), _NOW),
    )
    connection.execute(
        "INSERT INTO story_bible_heads "
        "(story_bible_id, revision_id, updated_at) "
        "VALUES (?, 'invalid-revision-id', ?)",
        (str(story_bible_id(1)), _NOW),
    )


def _invalid_revision_number(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    connection.execute(
        "INSERT INTO story_bible_revisions "
        "(id, story_bible_id, revision_number, title, content, created_at) "
        "VALUES (?, ?, 0, 'Valid', '', ?)",
        (str(story_bible_revision_id(11)), str(story_bible_id(1)), _NOW),
    )
    _head(connection, 1, 11)


def _invalid_content(connection: sqlite3.Connection) -> None:
    _stable(connection, 1)
    connection.execute(
        "INSERT INTO story_bible_revisions "
        "(id, story_bible_id, revision_number, title, content, created_at) "
        "VALUES (?, ?, 1, 'Valid', ?, ?)",
        (
            str(story_bible_revision_id(11)),
            str(story_bible_id(1)),
            "x" * 50_001,
            _NOW,
        ),
    )
    _head(connection, 1, 11)


def _invalid_time(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, created_at="not-a-time", updated_at="not-a-time")
    _revision(connection, 11, 1)
    _head(connection, 1, 11)


def _stable_updated_before_created(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, created_at=_LATER, updated_at=_EARLIER)
    _revision(connection, 11, 1, created_at=_LATER)
    _head(connection, 1, 11, updated_at=_EARLIER)


def _version_revision_mismatch(connection: sqlite3.Connection) -> None:
    _stable(connection, 1, version=2, updated_at=_NOW)
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
    _stable(connection, 1, created_at=_NOW, updated_at=_NOW)
    _revision(connection, 11, 1, created_at=_EARLIER)
    _head(connection, 1, 11, updated_at=_NOW)


@pytest.mark.parametrize(
    "corrupt",
    [
        _missing_head,
        _missing_revision,
        _ownership_mismatch,
        _invalid_stable_value,
        _invalid_revision_value,
        _inconsistent_times,
        _invalid_project_identifier,
        _invalid_revision_identifier,
        _invalid_revision_number,
        _invalid_content,
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

        with pytest.raises(StoryBibleDataCorruption) as captured:
            database.repository.get(story_bible_id(1))

    assert str(captured.value) == "The stored Story Bible state is inconsistent."
    assert "Valid" not in str(captured.value)


def test_get_for_project_detects_corruption_through_same_mapper(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            _invalid_stable_value(connection)
            connection.commit()

        with pytest.raises(StoryBibleDataCorruption):
            database.repository.get_for_project(project_id(1))


def test_get_for_project_rejects_multiple_story_bibles_as_cardinality_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        session = database.session_factory()

        def duplicate_rows(*_args: object, **_kwargs: object) -> object:
            raise MultipleResultsFound

        monkeypatch.setattr(session, "execute", duplicate_rows)
        repository = SqlAlchemyStoryBibleRepository(lambda: session)

        with pytest.raises(StoryBibleDataCorruption):
            repository.get_for_project(project_id(1))


@pytest.mark.parametrize("corruption", ["project-identity", "missing-head"])
def test_get_for_project_rejects_inconsistent_join_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    aggregate = story_bible_aggregate()
    stable, head, revision = story_bible_aggregate_to_records(aggregate)
    row = (
        (
            project_id(2),
            stable,
            head,
            revision,
        )
        if corruption == "project-identity"
        else (
            project_id(1),
            stable,
            None,
            revision,
        )
    )

    class OneRow:
        def one_or_none(self) -> object:
            return row

    with repository_database(tmp_path) as database:
        session = database.session_factory()
        monkeypatch.setattr(session, "execute", lambda *_args, **_kwargs: OneRow())

        with pytest.raises(StoryBibleDataCorruption):
            SqlAlchemyStoryBibleRepository._load_for_project(session, project_id(1))

        session.close()
