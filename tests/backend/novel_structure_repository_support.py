"""Deterministic fixtures for novel-structure persistence tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from tests.backend.test_novel_structure_migration import migrated_novel_structure_database_context

from aiwebnovel.db.session import create_database_session_factory
from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.novel_structure import (
    ChapterAggregate,
    ChapterId,
    ChapterRevisionId,
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
    OutlineAggregate,
    OutlineId,
    OutlineRevisionId,
    VolumeAggregate,
    VolumeId,
    VolumeRevisionId,
    create_initial_chapter,
    create_initial_outline,
    create_initial_volume,
)
from aiwebnovel.novel_structure.persistence.repository import SqlAlchemyNovelStructureRepository
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.repository import SqlAlchemyProjectRepository
from aiwebnovel.project.transitions import create_initial_project

BASE_TIME = datetime(2026, 8, 14, 1, 2, 3, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class NovelStructureRepositoryDatabase:
    engine: Engine
    session_factory: sessionmaker[Session]
    project_repository: SqlAlchemyProjectRepository
    repository: SqlAlchemyNovelStructureRepository


def project_id(value: int = 1) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_int(value))


def project_revision_id(value: int = 10_001) -> ProjectRevisionId:
    return ProjectRevisionId.from_ulid(Ulid.from_int(value))


def outline_id(value: int = 101) -> OutlineId:
    return OutlineId.from_ulid(Ulid.from_int(value))


def outline_revision_id(value: int = 10_101) -> OutlineRevisionId:
    return OutlineRevisionId.from_ulid(Ulid.from_int(value))


def volume_id(value: int = 201) -> VolumeId:
    return VolumeId.from_ulid(Ulid.from_int(value))


def volume_revision_id(value: int = 10_201) -> VolumeRevisionId:
    return VolumeRevisionId.from_ulid(Ulid.from_int(value))


def chapter_id(value: int = 301) -> ChapterId:
    return ChapterId.from_ulid(Ulid.from_int(value))


def chapter_revision_id(value: int = 10_301) -> ChapterRevisionId:
    return ChapterRevisionId.from_ulid(Ulid.from_int(value))


def project_aggregate(value: int = 1) -> ProjectAggregate:
    return create_initial_project(
        f"Project {value}",
        "",
        clock=lambda: BASE_TIME,
        project_id_factory=lambda: project_id(value),
        revision_id_factory=lambda: project_revision_id(10_000 + value),
    )


def outline_aggregate(value: int = 1, *, project_value: int = 1) -> OutlineAggregate:
    return create_initial_outline(
        outline_id=outline_id(100 + value),
        revision_id=outline_revision_id(10_100 + value),
        project_id=project_id(project_value),
        title=NovelStructureTitle(f"Outline {value}"),
        summary=NovelStructureSummary(f"Outline summary {value}"),
        now=BASE_TIME,
    )


def volume_aggregate(
    value: int = 1,
    *,
    project_value: int = 1,
    position: int | None = None,
) -> VolumeAggregate:
    return create_initial_volume(
        volume_id=volume_id(200 + value),
        revision_id=volume_revision_id(10_200 + value),
        project_id=project_id(project_value),
        title=NovelStructureTitle(f"Volume {value}"),
        summary=NovelStructureSummary(f"Volume summary {value}"),
        position=NovelStructurePosition(value if position is None else position),
        now=BASE_TIME,
    )


def chapter_aggregate(
    volume: VolumeAggregate,
    value: int = 1,
    *,
    project_value: int | None = None,
    position: int | None = None,
) -> ChapterAggregate:
    owner = volume.volume.project_id if project_value is None else project_id(project_value)
    domain_volume = volume.volume
    if owner != domain_volume.project_id:
        domain_volume = type(domain_volume)(
            id=domain_volume.id,
            project_id=owner,
            concurrency_version=domain_volume.concurrency_version,
            created_at=domain_volume.created_at,
            updated_at=domain_volume.updated_at,
        )
    return create_initial_chapter(
        chapter_id=chapter_id(300 + value),
        revision_id=chapter_revision_id(10_300 + value),
        project_id=owner,
        volume=domain_volume,
        title=NovelStructureTitle(f"Chapter {value}"),
        summary=NovelStructureSummary(f"Chapter summary {value}"),
        position=NovelStructurePosition(value if position is None else position),
        now=BASE_TIME,
    )


def later(seconds: int = 1) -> datetime:
    return BASE_TIME + timedelta(seconds=seconds)


@contextmanager
def repository_database(tmp_path: Path) -> Iterator[NovelStructureRepositoryDatabase]:
    with migrated_novel_structure_database_context(tmp_path) as migrated:
        session_factory = create_database_session_factory(migrated.engine)
        yield NovelStructureRepositoryDatabase(
            engine=migrated.engine,
            session_factory=session_factory,
            project_repository=SqlAlchemyProjectRepository(session_factory),
            repository=SqlAlchemyNovelStructureRepository(session_factory),
        )


def create_project(
    database: NovelStructureRepositoryDatabase,
    value: int = 1,
) -> ProjectAggregate:
    aggregate = project_aggregate(value)
    database.project_repository.create(aggregate)
    return aggregate
