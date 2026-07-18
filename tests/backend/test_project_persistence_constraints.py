"""SQLite constraints for Project identity, revisions, and head ownership."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, inspect
from sqlalchemy.exc import IntegrityError
from tests.backend.test_project_migration import (
    MigratedProjectDatabase,
    migrated_project_database_context,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.models import (
    ProjectHeadRecord,
    ProjectRecord,
    ProjectRevisionRecord,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)
_PYTHON_STRIP_WHITESPACE_CODE_POINTS = (
    9,
    10,
    11,
    12,
    13,
    28,
    29,
    30,
    31,
    32,
    133,
    160,
    5760,
    *range(8192, 8203),
    8232,
    8233,
    8239,
    8287,
    12288,
)


@pytest.fixture(name="migrated_project_database")
def _migrated_project_database_fixture(
    tmp_path: Path,
) -> Iterator[MigratedProjectDatabase]:
    with migrated_project_database_context(tmp_path) as database:
        yield database


def _project_id(value: int) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_int(value))


def _revision_id(value: int) -> ProjectRevisionId:
    return ProjectRevisionId.from_ulid(Ulid.from_int(value))


def _insert_project(
    connection: Connection,
    project_id: ProjectId,
    *,
    concurrency_version: int = 1,
) -> None:
    connection.execute(
        ProjectRecord.__table__.insert().values(
            id=project_id,
            concurrency_version=ConcurrencyVersion(concurrency_version),
            created_at=_NOW,
            updated_at=_NOW,
        )
    )


def _insert_revision(
    connection: Connection,
    revision_id: ProjectRevisionId,
    project_id: ProjectId,
    revision_number: int,
    *,
    title: str = "Project title",
    description: str = "Project description",
    created_at: datetime = _NOW,
) -> None:
    connection.execute(
        ProjectRevisionRecord.__table__.insert().values(
            id=revision_id,
            project_id=project_id,
            revision_number=RevisionNumber(revision_number),
            title=title,
            description=description,
            created_at=created_at,
        )
    )


def _insert_head(
    connection: Connection,
    project_id: ProjectId,
    revision_id: ProjectRevisionId,
    *,
    updated_at: datetime = _NOW,
) -> None:
    connection.execute(
        ProjectHeadRecord.__table__.insert().values(
            project_id=project_id,
            revision_id=revision_id,
            updated_at=updated_at,
        )
    )


def test_migrated_schema_has_required_keys_unique_constraints_and_index(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    engine = migrated_project_database.engine
    database = inspect(engine)

    assert set(database.get_table_names()) == {
        "alembic_version",
        "projects",
        "project_revisions",
        "project_heads",
    }
    assert database.get_pk_constraint("projects")["constrained_columns"] == ["id"]
    assert database.get_pk_constraint("project_revisions")["constrained_columns"] == ["id"]
    assert database.get_pk_constraint("project_heads")["constrained_columns"] == ["project_id"]
    unique_columns = {
        tuple(constraint["column_names"])
        for constraint in database.get_unique_constraints("project_revisions")
    }
    assert unique_columns == {
        ("project_id", "revision_number"),
        ("project_id", "id"),
    }
    indexes = {
        index["name"]: tuple(index["column_names"])
        for index in database.get_indexes("project_revisions")
    }
    assert indexes["ix_project_revisions_project_id_revision_number"] == (
        "project_id",
        "revision_number",
    )
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1


def test_head_composite_foreign_key_matches_project_and_revision_ownership(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    engine = migrated_project_database.engine
    with engine.connect() as connection:
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_key_list(project_heads)").all()

    revision_foreign_key_rows = [row for row in foreign_keys if row[2] == "project_revisions"]
    assert {(row[3], row[4]) for row in revision_foreign_key_rows} == {
        ("project_id", "project_id"),
        ("revision_id", "id"),
    }
    assert len({row[0] for row in revision_foreign_key_rows}) == 1
    assert any(
        row[2] == "projects" and row[3] == "project_id" and row[4] == "id" for row in foreign_keys
    )

    first_project = _project_id(1)
    second_project = _project_id(2)
    first_revision = _revision_id(11)
    with engine.begin() as connection:
        _insert_project(connection, first_project)
        _insert_project(connection, second_project)
        _insert_revision(connection, first_revision, first_project, 1)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_head(connection, second_project, first_revision)


def test_revision_requires_project_and_head_requires_both_owners(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    engine = migrated_project_database.engine
    missing_project = _project_id(100)
    missing_revision = _revision_id(101)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_revision(connection, missing_revision, missing_project, 1)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_head(connection, missing_project, missing_revision)

    existing_project = _project_id(102)
    with engine.begin() as connection:
        _insert_project(connection, existing_project)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_head(connection, existing_project, missing_revision)


def test_revision_number_is_unique_per_project_but_restarts_for_another_project(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    engine = migrated_project_database.engine
    first_project = _project_id(200)
    second_project = _project_id(201)
    with engine.begin() as connection:
        _insert_project(connection, first_project)
        _insert_project(connection, second_project)
        _insert_revision(connection, _revision_id(210), first_project, 1)
        _insert_revision(connection, _revision_id(211), second_project, 1)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_revision(connection, _revision_id(212), first_project, 1)


def test_one_project_has_one_head_and_head_can_move_to_its_next_revision(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    engine = migrated_project_database.engine
    project_id = _project_id(300)
    first_revision = _revision_id(301)
    second_revision = _revision_id(302)
    with engine.begin() as connection:
        _insert_project(connection, project_id)
        _insert_revision(connection, first_revision, project_id, 1)
        _insert_revision(
            connection,
            second_revision,
            project_id,
            2,
            created_at=_NOW + timedelta(seconds=1),
        )
        _insert_head(connection, project_id, first_revision)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_head(
            connection, project_id, second_revision, updated_at=_NOW + timedelta(seconds=1)
        )

    with engine.begin() as connection:
        result = connection.execute(
            ProjectHeadRecord.__table__.update()
            .where(ProjectHeadRecord.project_id == project_id)
            .values(
                revision_id=second_revision,
                updated_at=_NOW + timedelta(seconds=1),
            )
        )
        assert result.rowcount == 1

    with engine.connect() as connection:
        assert (
            connection.execute(
                ProjectHeadRecord.__table__.select().where(
                    ProjectHeadRecord.project_id == project_id
                )
            )
            .one()
            .revision_id
            == second_revision
        )


def test_database_checks_positive_versions_and_bounded_project_text(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    engine = migrated_project_database.engine
    timestamp = "2026-02-03 04:05:06.000000"
    project_id = _project_id(400)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO projects (id, concurrency_version, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (str(project_id), 0, timestamp, timestamp),
        )

    with engine.begin() as connection:
        _insert_project(connection, project_id)

    invalid_revisions = (
        (_revision_id(401), 0, "valid", ""),
        (_revision_id(402), 1, "", ""),
        (_revision_id(403), 2, "x" * 121, ""),
        (_revision_id(404), 3, "valid", "x" * 2001),
    )
    for revision_id, revision_number, title, description in invalid_revisions:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO project_revisions "
                "(id, project_id, revision_number, title, description, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(revision_id),
                    str(project_id),
                    revision_number,
                    title,
                    description,
                    timestamp,
                ),
            )

    for offset, code_point in enumerate(_PYTHON_STRIP_WHITESPACE_CODE_POINTS, start=1):
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO project_revisions "
                "(id, project_id, revision_number, title, description, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(_revision_id(500 + offset)),
                    str(project_id),
                    10 + offset,
                    chr(code_point),
                    "",
                    timestamp,
                ),
            )


def test_deleting_project_never_cascades_immutable_revision_history(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    engine = migrated_project_database.engine
    project_id = _project_id(500)
    with engine.begin() as connection:
        _insert_project(connection, project_id)
        _insert_revision(connection, _revision_id(501), project_id, 1)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(ProjectRecord.__table__.delete().where(ProjectRecord.id == project_id))

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM projects").scalar_one() == 1
        assert (
            connection.exec_driver_sql("SELECT COUNT(*) FROM project_revisions").scalar_one() == 1
        )
