"""SQLite constraints for Story Bible ownership, revisions, and heads."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, inspect
from sqlalchemy.exc import IntegrityError
from tests.backend.story_bible_repository_support import (
    create_project,
    project_id,
    repository_database,
    story_bible_id,
    story_bible_revision_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.persistence.models import (
    StoryBibleHeadRecord,
    StoryBibleRecord,
    StoryBibleRevisionRecord,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 7, 8, 9, 10, tzinfo=UTC)


@pytest.fixture(name="database")
def _database_fixture(tmp_path: Path) -> Iterator[object]:
    with repository_database(tmp_path) as database:
        create_project(database)
        create_project(database, 2)
        yield database


def _insert_stable(
    connection: Connection,
    identifier: int,
    *,
    project: int = 1,
    concurrency_version: int = 1,
) -> StoryBibleId:
    owner = story_bible_id(identifier)
    connection.execute(
        StoryBibleRecord.__table__.insert().values(
            id=owner,
            project_id=project_id(project),
            concurrency_version=ConcurrencyVersion(concurrency_version),
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    return owner


def _insert_revision(
    connection: Connection,
    identifier: int,
    owner: StoryBibleId,
    revision_number: int = 1,
) -> StoryBibleRevisionId:
    revision = story_bible_revision_id(identifier)
    connection.execute(
        StoryBibleRevisionRecord.__table__.insert().values(
            id=revision,
            story_bible_id=owner,
            revision_number=RevisionNumber(revision_number),
            title="Valid",
            content="",
            created_at=_NOW,
        )
    )
    return revision


def _insert_head(
    connection: Connection,
    owner: StoryBibleId,
    revision: StoryBibleRevisionId,
) -> None:
    connection.execute(
        StoryBibleHeadRecord.__table__.insert().values(
            story_bible_id=owner,
            revision_id=revision,
            updated_at=_NOW,
        )
    )


def test_schema_has_exact_keys_unique_constraints_and_foreign_keys(database: object) -> None:
    engine = database.engine  # type: ignore[attr-defined]
    schema = inspect(engine)

    assert schema.get_pk_constraint("story_bibles")["constrained_columns"] == ["id"]
    assert schema.get_pk_constraint("story_bible_revisions")["constrained_columns"] == ["id"]
    assert schema.get_pk_constraint("story_bible_heads")["constrained_columns"] == [
        "story_bible_id"
    ]
    assert {
        tuple(item["column_names"]) for item in schema.get_unique_constraints("story_bibles")
    } == {("project_id",)}
    assert {
        tuple(item["column_names"])
        for item in schema.get_unique_constraints("story_bible_revisions")
    } == {
        ("story_bible_id", "revision_number"),
        ("story_bible_id", "id"),
    }
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        head_fks = connection.exec_driver_sql("PRAGMA foreign_key_list(story_bible_heads)").all()
    revision_fk_rows = [row for row in head_fks if row[2] == "story_bible_revisions"]
    assert {(row[3], row[4]) for row in revision_fk_rows} == {
        ("story_bible_id", "story_bible_id"),
        ("revision_id", "id"),
    }
    assert len({row[0] for row in revision_fk_rows}) == 1


def test_project_ownership_is_required_unique_and_restricts_delete(database: object) -> None:
    engine = database.engine  # type: ignore[attr-defined]
    with engine.begin() as connection:
        owner = _insert_stable(connection, 1)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_stable(connection, 2)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_stable(connection, 3, project=404)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM projects WHERE id = ?",
            (str(project_id(1)),),
        )

    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT project_id FROM story_bibles WHERE id = ?",
            (str(owner),),
        ).scalar_one() == str(project_id(1))


def test_revision_constraints_and_head_composite_ownership(database: object) -> None:
    engine = database.engine  # type: ignore[attr-defined]
    with engine.begin() as connection:
        first_owner = _insert_stable(connection, 1)
        second_owner = _insert_stable(connection, 2, project=2)
        first_revision = _insert_revision(connection, 11, first_owner)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_revision(connection, 12, first_owner, 1)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO story_bible_revisions "
            "(id, story_bible_id, revision_number, title, content, created_at) "
            "VALUES (?, ?, 0, 'Valid', '', ?)",
            (str(story_bible_revision_id(13)), str(first_owner), _NOW.isoformat()),
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_head(connection, second_owner, first_revision)

    with engine.begin() as connection:
        _insert_head(connection, first_owner, first_revision)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_head(connection, first_owner, first_revision)


@pytest.mark.parametrize(
    ("title", "content"),
    [
        ("", ""),
        (" ", ""),
        ("x" * 121, ""),
        ("Valid", "x" * 50_001),
    ],
    ids=("empty-title", "blank-title", "long-title", "long-content"),
)
def test_revision_text_bounds_are_enforced(
    database: object,
    title: str,
    content: str,
) -> None:
    engine = database.engine  # type: ignore[attr-defined]
    with engine.begin() as connection:
        owner = _insert_stable(connection, 10)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO story_bible_revisions "
            "(id, story_bible_id, revision_number, title, content, created_at) "
            "VALUES (?, ?, 1, ?, ?, ?)",
            (
                str(story_bible_revision_id(100)),
                str(owner),
                title,
                content,
                _NOW.isoformat(),
            ),
        )
