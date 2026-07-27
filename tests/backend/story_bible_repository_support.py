"""Shared deterministic fixtures for Story Bible persistence tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from tests.backend.test_story_bible_migration import (
    migrated_story_bible_database_context,
)

from aiwebnovel.db.session import create_database_session_factory
from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.repository import SqlAlchemyProjectRepository
from aiwebnovel.project.transitions import create_initial_project
from aiwebnovel.story_bible.entities import StoryBibleAggregate
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.persistence.repository import (
    SqlAlchemyStoryBibleRepository,
)
from aiwebnovel.story_bible.transitions import create_initial_story_bible
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

BASE_TIME = datetime(2026, 6, 7, 8, 9, 10, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class StoryBibleRepositoryDatabase:
    """Migrated isolated database with both owner and Story Bible adapters."""

    engine: Engine
    session_factory: sessionmaker[Session]
    project_repository: SqlAlchemyProjectRepository
    repository: SqlAlchemyStoryBibleRepository


def project_id(value: int) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_int(value))


def project_revision_id(value: int) -> ProjectRevisionId:
    return ProjectRevisionId.from_ulid(Ulid.from_int(value))


def story_bible_id(value: int) -> StoryBibleId:
    return StoryBibleId.from_ulid(Ulid.from_int(value))


def story_bible_revision_id(value: int) -> StoryBibleRevisionId:
    return StoryBibleRevisionId.from_ulid(Ulid.from_int(value))


def project_aggregate(value: int = 1) -> ProjectAggregate:
    return create_initial_project(
        f"Project {value}",
        "",
        clock=lambda: BASE_TIME,
        project_id_factory=lambda: project_id(value),
        revision_id_factory=lambda: project_revision_id(10_000 + value),
    )


def story_bible_aggregate(
    value: int = 1,
    *,
    project_value: int | None = None,
    revision_value: int | None = None,
    title: str = "Story Bible",
    content: str = "Initial setting",
    created_at: datetime = BASE_TIME,
) -> StoryBibleAggregate:
    project_value = value if project_value is None else project_value
    revision_value = 20_000 + value if revision_value is None else revision_value
    return create_initial_story_bible(
        story_bible_id=story_bible_id(value),
        revision_id=story_bible_revision_id(revision_value),
        project_id=project_id(project_value),
        title=StoryBibleTitle(title),
        content=StoryBibleContent(content),
        now=created_at,
    )


def later(seconds: int = 1) -> datetime:
    return BASE_TIME + timedelta(seconds=seconds)


@contextmanager
def repository_database(tmp_path: Path) -> Iterator[StoryBibleRepositoryDatabase]:
    """Migrate and fully dispose one Story Bible repository database."""
    with migrated_story_bible_database_context(tmp_path) as migrated:
        session_factory = create_database_session_factory(migrated.engine)
        project_repository = SqlAlchemyProjectRepository(session_factory)
        yield StoryBibleRepositoryDatabase(
            engine=migrated.engine,
            session_factory=session_factory,
            project_repository=project_repository,
            repository=SqlAlchemyStoryBibleRepository(session_factory),
        )


def create_project(
    database: StoryBibleRepositoryDatabase,
    value: int = 1,
) -> ProjectAggregate:
    aggregate = project_aggregate(value)
    database.project_repository.create(aggregate)
    return aggregate


def table_state(engine: Engine) -> dict[str, Any]:
    """Return exact Story Bible row counts and current scalar state."""
    with engine.connect() as connection:
        counts = {
            table: connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
            for table in (
                "story_bibles",
                "story_bible_revisions",
                "story_bible_heads",
            )
        }
        stable = connection.exec_driver_sql(
            "SELECT concurrency_version, updated_at FROM story_bibles ORDER BY id LIMIT 1"
        ).first()
        head = connection.exec_driver_sql(
            "SELECT revision_id, updated_at FROM story_bible_heads ORDER BY story_bible_id LIMIT 1"
        ).first()
        return {
            **counts,
            "concurrency_version": None if stable is None else stable[0],
            "stable_updated_at": None if stable is None else stable[1],
            "head_revision_id": None if head is None else head[0],
            "head_updated_at": None if head is None else head[1],
        }
