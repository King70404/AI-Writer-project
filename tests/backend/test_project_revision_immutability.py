"""Database-trigger enforcement for immutable Project revisions."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.backend.test_project_migration import (
    MigratedProjectDatabase,
    migrated_project_database_context,
)
from tests.backend.test_project_persistence_constraints import (
    _insert_project,
    _insert_revision,
    _project_id,
    _revision_id,
)

from aiwebnovel.project.identifiers import ProjectRevisionId
from aiwebnovel.project.persistence.models import ProjectRevisionRecord

pytestmark = pytest.mark.integration

_IMMUTABLE_MESSAGE = "Project revisions are immutable"


@pytest.fixture(name="migrated_project_database")
def _migrated_project_database_fixture(
    tmp_path: Path,
) -> Iterator[MigratedProjectDatabase]:
    with migrated_project_database_context(tmp_path) as database:
        yield database


def _seed_revisions(
    database: MigratedProjectDatabase,
) -> tuple[ProjectRevisionId, ProjectRevisionId]:
    project_id = _project_id(700)
    first_revision = _revision_id(701)
    second_revision = _revision_id(702)
    with database.engine.begin() as connection:
        _insert_project(connection, project_id)
        _insert_revision(
            connection,
            first_revision,
            project_id,
            1,
            title="private update canary",
        )
        _insert_revision(
            connection,
            second_revision,
            project_id,
            2,
            title="private delete canary",
        )
    return first_revision, second_revision


def test_revision_triggers_exist_once_with_stable_names(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    with migrated_project_database.engine.connect() as connection:
        triggers = list(
            connection.exec_driver_sql(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'trigger' AND tbl_name = 'project_revisions' ORDER BY name"
            ).scalars()
        )

    assert triggers == [
        "trg_project_revisions_no_delete",
        "trg_project_revisions_no_update",
    ]


def test_direct_sql_update_and_delete_are_rejected_by_safe_trigger_errors(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    first_revision, second_revision = _seed_revisions(migrated_project_database)
    engine = migrated_project_database.engine

    with pytest.raises(IntegrityError) as update_error, engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE project_revisions SET title = ? WHERE id = ?",
            ("attempted replacement", str(first_revision)),
        )
    assert str(update_error.value.orig) == _IMMUTABLE_MESSAGE
    assert "private update canary" not in str(update_error.value.orig)

    with pytest.raises(IntegrityError) as delete_error, engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM project_revisions WHERE id = ?",
            (str(second_revision),),
        )
    assert str(delete_error.value.orig) == _IMMUTABLE_MESSAGE
    assert "private delete canary" not in str(delete_error.value.orig)

    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT COUNT(*) FROM project_revisions").scalar_one() == 2
        )


def test_orm_update_and_delete_are_rejected_without_hiding_failure(
    migrated_project_database: MigratedProjectDatabase,
) -> None:
    first_revision, second_revision = _seed_revisions(migrated_project_database)
    engine = migrated_project_database.engine

    with Session(engine) as session:
        record = session.get(ProjectRevisionRecord, first_revision)
        assert record is not None
        record.title = "ORM attempted replacement"
        with pytest.raises(IntegrityError) as update_error:
            session.commit()
        assert str(update_error.value.orig) == _IMMUTABLE_MESSAGE
        session.rollback()

    with Session(engine) as session:
        record = session.get(ProjectRevisionRecord, second_revision)
        assert record is not None
        session.delete(record)
        with pytest.raises(IntegrityError) as delete_error:
            session.commit()
        assert str(delete_error.value.orig) == _IMMUTABLE_MESSAGE
        session.rollback()

    with engine.connect() as connection:
        rows = list(
            connection.exec_driver_sql(
                "SELECT title FROM project_revisions ORDER BY revision_number"
            ).scalars()
        )
        assert rows == ["private update canary", "private delete canary"]
