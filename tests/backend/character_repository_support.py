"""Shared deterministic fixtures for Character persistence tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from tests.backend.test_character_migration import (
    migrated_character_database_context,
)

from aiwebnovel.character.entities import CharacterAggregate
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.persistence.repository import SqlAlchemyCharacterRepository
from aiwebnovel.character.transitions import create_initial_character
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.db.session import create_database_session_factory
from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.repository import SqlAlchemyProjectRepository
from aiwebnovel.project.transitions import create_initial_project

BASE_TIME = datetime(2026, 7, 29, 8, 9, 10, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class CharacterRepositoryDatabase:
    """Migrated isolated database with owner and Character adapters."""

    engine: Engine
    session_factory: sessionmaker[Session]
    project_repository: SqlAlchemyProjectRepository
    repository: SqlAlchemyCharacterRepository


def project_id(value: int) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_int(value))


def project_revision_id(value: int) -> ProjectRevisionId:
    return ProjectRevisionId.from_ulid(Ulid.from_int(value))


def character_id(value: int) -> CharacterId:
    return CharacterId.from_ulid(Ulid.from_int(value))


def character_revision_id(value: int) -> CharacterRevisionId:
    return CharacterRevisionId.from_ulid(Ulid.from_int(value))


def project_aggregate(value: int = 1) -> ProjectAggregate:
    return create_initial_project(
        f"Project {value}",
        "",
        clock=lambda: BASE_TIME,
        project_id_factory=lambda: project_id(value),
        revision_id_factory=lambda: project_revision_id(10_000 + value),
    )


def character_aggregate(
    value: int = 1,
    *,
    project_value: int | None = None,
    revision_value: int | None = None,
    name: str = "Character",
    role: str = "Protagonist",
    profile: str = "Initial profile",
    created_at: datetime = BASE_TIME,
) -> CharacterAggregate:
    project_value = value if project_value is None else project_value
    revision_value = 20_000 + value if revision_value is None else revision_value
    return create_initial_character(
        character_id=character_id(value),
        revision_id=character_revision_id(revision_value),
        project_id=project_id(project_value),
        name=CharacterName(name),
        role=CharacterRole(role),
        profile=CharacterProfile(profile),
        now=created_at,
    )


def later(seconds: int = 1) -> datetime:
    return BASE_TIME + timedelta(seconds=seconds)


@contextmanager
def repository_database(tmp_path: Path) -> Iterator[CharacterRepositoryDatabase]:
    """Migrate and fully dispose one Character repository database."""
    with migrated_character_database_context(tmp_path) as migrated:
        session_factory = create_database_session_factory(migrated.engine)
        project_repository = SqlAlchemyProjectRepository(session_factory)
        yield CharacterRepositoryDatabase(
            engine=migrated.engine,
            session_factory=session_factory,
            project_repository=project_repository,
            repository=SqlAlchemyCharacterRepository(session_factory),
        )


def create_project(
    database: CharacterRepositoryDatabase,
    value: int = 1,
) -> ProjectAggregate:
    aggregate = project_aggregate(value)
    database.project_repository.create(aggregate)
    return aggregate


def table_state(engine: Engine, character_value: int = 1) -> dict[str, Any]:
    """Return exact row counts and one Character's current scalar state."""
    with engine.connect() as connection:
        counts = {
            table: connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
            for table in ("characters", "character_revisions", "character_heads")
        }
        stable = connection.exec_driver_sql(
            "SELECT concurrency_version, updated_at FROM characters WHERE id = ?",
            (str(character_id(character_value)),),
        ).first()
        head = connection.exec_driver_sql(
            "SELECT revision_id, updated_at FROM character_heads WHERE character_id = ?",
            (str(character_id(character_value)),),
        ).first()
        return {
            **counts,
            "concurrency_version": None if stable is None else stable[0],
            "stable_updated_at": None if stable is None else stable[1],
            "head_revision_id": None if head is None else head[0],
            "head_updated_at": None if head is None else head[1],
        }
