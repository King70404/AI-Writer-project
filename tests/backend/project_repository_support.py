"""Shared deterministic fixtures for Project repository contract tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from tests.backend.test_project_migration import migrated_project_database_context

from aiwebnovel.db.session import create_database_session_factory
from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.repository import SqlAlchemyProjectRepository
from aiwebnovel.project.transitions import create_initial_project

BASE_TIME = datetime(2026, 4, 5, 6, 7, 8, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class RepositoryDatabase:
    """Migrated temporary database with one repository-ready Session factory."""

    engine: Engine
    session_factory: sessionmaker[Session]
    repository: SqlAlchemyProjectRepository


def project_id(value: int) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_int(value))


def revision_id(value: int) -> ProjectRevisionId:
    return ProjectRevisionId.from_ulid(Ulid.from_int(value))


def aggregate(
    value: int = 1,
    *,
    revision_value: int | None = None,
    title: str = "Repository project",
    description: str = "Repository description",
    created_at: datetime = BASE_TIME,
) -> ProjectAggregate:
    revision_value = value + 10_000 if revision_value is None else revision_value
    return create_initial_project(
        title,
        description,
        clock=lambda: created_at,
        project_id_factory=lambda: project_id(value),
        revision_id_factory=lambda: revision_id(revision_value),
    )


def later(seconds: int = 1) -> datetime:
    return BASE_TIME + timedelta(seconds=seconds)


@contextmanager
def repository_database(tmp_path: Path) -> Iterator[RepositoryDatabase]:
    """Migrate and dispose one isolated repository test database."""
    with migrated_project_database_context(tmp_path) as migrated:
        session_factory = create_database_session_factory(migrated.engine)
        yield RepositoryDatabase(
            engine=migrated.engine,
            session_factory=session_factory,
            repository=SqlAlchemyProjectRepository(session_factory),
        )


def table_state(engine: Engine) -> dict[str, Any]:
    """Read Project table counts and the current scalar state directly."""
    with engine.connect() as connection:
        counts = {
            table: connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
            for table in ("projects", "project_revisions", "project_heads")
        }
        project = connection.exec_driver_sql(
            "SELECT concurrency_version FROM projects ORDER BY id LIMIT 1"
        ).first()
        head = connection.exec_driver_sql(
            "SELECT revision_id FROM project_heads ORDER BY project_id LIMIT 1"
        ).first()
        return {
            **counts,
            "concurrency_version": None if project is None else project[0],
            "head_revision_id": None if head is None else head[0],
        }
