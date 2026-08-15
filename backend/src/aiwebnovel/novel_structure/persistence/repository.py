"""Transactional SQLAlchemy implementation for novel structure."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.time import Clock
from aiwebnovel.novel_structure.entities import ChapterAggregate, OutlineAggregate, VolumeAggregate
from aiwebnovel.novel_structure.errors import (
    ChapterAlreadyExists,
    ChapterNotFound,
    ChapterPositionConflict,
    ChapterVolumeOwnershipMismatch,
    InvalidNovelStructureState,
    NovelStructureDataCorruption,
    NovelStructureProjectNotFound,
    NovelStructureRepositoryError,
    OutlineAlreadyExists,
    OutlineNotFound,
    VolumeAlreadyExists,
    VolumeNotFound,
    VolumePositionConflict,
)
from aiwebnovel.novel_structure.identifiers import (
    ChapterId,
    ChapterRevisionId,
    OutlineId,
    OutlineRevisionId,
    VolumeId,
    VolumeRevisionId,
)
from aiwebnovel.novel_structure.persistence.mappers import (
    chapter_aggregate_from_records,
    chapter_aggregate_to_records,
    chapter_revision_to_record,
    outline_aggregate_from_records,
    outline_aggregate_to_records,
    outline_revision_to_record,
    volume_aggregate_from_records,
    volume_aggregate_to_records,
    volume_revision_to_record,
)
from aiwebnovel.novel_structure.persistence.models import (
    ChapterRecord,
    OutlineRecord,
    VolumeRecord,
)
from aiwebnovel.novel_structure.persistence.queries import (
    chapter_head_compare_and_swap,
    chapter_identity_query,
    chapter_position_query,
    chapters_for_volume_query,
    current_chapter_query,
    current_outline_for_project_query,
    current_outline_query,
    current_volume_query,
    outline_for_project_identity_query,
    outline_head_compare_and_swap,
    outline_identity_query,
    project_exists_query,
    stable_compare_and_swap,
    volume_head_compare_and_swap,
    volume_identity_query,
    volume_owner_query,
    volume_position_query,
    volumes_for_project_query,
)
from aiwebnovel.novel_structure.repository import NovelStructureRepository
from aiwebnovel.novel_structure.transitions import (
    append_chapter_revision,
    append_outline_revision,
    append_volume_revision,
)
from aiwebnovel.novel_structure.values import (
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)
from aiwebnovel.project.identifiers import ProjectId

SessionFactory = Callable[[], Session]
T = TypeVar("T")


class SqlAlchemyNovelStructureRepository(NovelStructureRepository):
    """Use one independent BEGIN IMMEDIATE transaction per write."""

    def __init__(self, session_factory: SessionFactory) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def create_outline(self, aggregate: OutlineAggregate) -> OutlineAggregate:
        self._validate_initial(aggregate, OutlineAggregate, "outline")
        session = self._new_session()
        try:
            self._begin_immediate(session)
            project_id = aggregate.outline.project_id
            if session.scalar(project_exists_query(project_id)) is None:
                raise NovelStructureProjectNotFound
            if (
                session.scalar(outline_identity_query(aggregate.outline.id)) is not None
                or session.scalar(outline_for_project_identity_query(project_id)) is not None
            ):
                raise OutlineAlreadyExists
            stable, head, revision = outline_aggregate_to_records(aggregate)
            self._insert_three(session, stable, revision, head)
            session.commit()
            return aggregate
        except DomainError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise NovelStructureRepositoryError from exc
        finally:
            session.close()

    def get_outline(self, outline_id: OutlineId) -> OutlineAggregate | None:
        if type(outline_id) is not OutlineId:
            raise InvalidNovelStructureState
        return self._read_one(lambda session: self._load_outline(session, outline_id))

    def get_outline_for_project(self, project_id: ProjectId) -> OutlineAggregate | None:
        if type(project_id) is not ProjectId:
            raise InvalidNovelStructureState

        def load(session: Session) -> OutlineAggregate | None:
            row = session.execute(current_outline_for_project_query(project_id)).one_or_none()
            return None if row is None else self._outline_from_row(row)

        return self._read_one(load)

    def append_outline_revision(
        self,
        outline_id: OutlineId,
        *,
        expected_version: ConcurrencyVersion,
        title: NovelStructureTitle,
        summary: NovelStructureSummary,
        clock: Clock,
        revision_id_factory: Callable[[], OutlineRevisionId],
    ) -> OutlineAggregate:
        self._validate_append(
            outline_id,
            OutlineId,
            expected_version,
            title,
            summary,
            clock,
            revision_id_factory,
        )
        session = self._new_session()
        try:
            self._begin_immediate(session)
            current = self._load_outline(session, outline_id)
            if current is None:
                raise OutlineNotFound
            assert_expected_version(current.outline.concurrency_version, expected_version)
            next_aggregate = append_outline_revision(
                current,
                expected_version=expected_version,
                revision_id=revision_id_factory(),
                title=title,
                summary=summary,
                now=clock(),
            )
            session.add(outline_revision_to_record(next_aggregate.current_revision))
            session.flush()
            self._move_outline(session, current, next_aggregate)
            session.commit()
            return next_aggregate
        except DomainError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise NovelStructureRepositoryError from exc
        finally:
            session.close()

    def create_volume(self, aggregate: VolumeAggregate) -> VolumeAggregate:
        self._validate_initial(aggregate, VolumeAggregate, "volume")
        session = self._new_session()
        try:
            self._begin_immediate(session)
            project_id = aggregate.volume.project_id
            if session.scalar(project_exists_query(project_id)) is None:
                raise NovelStructureProjectNotFound
            if session.scalar(volume_identity_query(aggregate.volume.id)) is not None:
                raise VolumeAlreadyExists
            if (
                session.scalar(
                    volume_position_query(project_id, int(aggregate.current_revision.position))
                )
                is not None
            ):
                raise VolumePositionConflict
            stable, head, revision = volume_aggregate_to_records(aggregate)
            self._insert_three(session, stable, revision, head)
            session.commit()
            return aggregate
        except DomainError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise NovelStructureRepositoryError from exc
        finally:
            session.close()

    def get_volume(self, volume_id: VolumeId) -> VolumeAggregate | None:
        if type(volume_id) is not VolumeId:
            raise InvalidNovelStructureState
        return self._read_one(lambda session: self._load_volume(session, volume_id))

    def list_volumes_for_project(self, project_id: ProjectId) -> tuple[VolumeAggregate, ...]:
        if type(project_id) is not ProjectId:
            raise InvalidNovelStructureState
        return self._read_many(
            lambda session: tuple(
                self._volume_from_row(row)
                for row in session.execute(volumes_for_project_query(project_id)).all()
            )
        )

    def append_volume_revision(
        self,
        volume_id: VolumeId,
        *,
        expected_version: ConcurrencyVersion,
        title: NovelStructureTitle,
        summary: NovelStructureSummary,
        position: NovelStructurePosition,
        clock: Clock,
        revision_id_factory: Callable[[], VolumeRevisionId],
    ) -> VolumeAggregate:
        self._validate_append(
            volume_id,
            VolumeId,
            expected_version,
            title,
            summary,
            clock,
            revision_id_factory,
            position,
        )
        session = self._new_session()
        try:
            self._begin_immediate(session)
            current = self._load_volume(session, volume_id)
            if current is None:
                raise VolumeNotFound
            assert_expected_version(current.volume.concurrency_version, expected_version)
            if (
                session.scalar(
                    volume_position_query(
                        current.volume.project_id,
                        int(position),
                        exclude_id=volume_id,
                    )
                )
                is not None
            ):
                raise VolumePositionConflict
            next_aggregate = append_volume_revision(
                current,
                expected_version=expected_version,
                revision_id=revision_id_factory(),
                title=title,
                summary=summary,
                position=position,
                now=clock(),
            )
            session.add(volume_revision_to_record(next_aggregate.current_revision))
            session.flush()
            self._move_volume(session, current, next_aggregate)
            session.commit()
            return next_aggregate
        except DomainError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise NovelStructureRepositoryError from exc
        finally:
            session.close()

    def create_chapter(self, aggregate: ChapterAggregate) -> ChapterAggregate:
        self._validate_initial(aggregate, ChapterAggregate, "chapter")
        session = self._new_session()
        try:
            self._begin_immediate(session)
            project_id = aggregate.chapter.project_id
            if session.scalar(project_exists_query(project_id)) is None:
                raise NovelStructureProjectNotFound
            volume_project_id = session.scalar(volume_owner_query(aggregate.chapter.volume_id))
            if volume_project_id is None:
                raise VolumeNotFound
            if volume_project_id != project_id:
                raise ChapterVolumeOwnershipMismatch
            if session.scalar(chapter_identity_query(aggregate.chapter.id)) is not None:
                raise ChapterAlreadyExists
            if (
                session.scalar(
                    chapter_position_query(
                        aggregate.chapter.volume_id,
                        int(aggregate.current_revision.position),
                    )
                )
                is not None
            ):
                raise ChapterPositionConflict
            stable, head, revision = chapter_aggregate_to_records(aggregate)
            self._insert_three(session, stable, revision, head)
            session.commit()
            return aggregate
        except DomainError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise NovelStructureRepositoryError from exc
        finally:
            session.close()

    def get_chapter(self, chapter_id: ChapterId) -> ChapterAggregate | None:
        if type(chapter_id) is not ChapterId:
            raise InvalidNovelStructureState
        return self._read_one(lambda session: self._load_chapter(session, chapter_id))

    def list_chapters_for_volume(self, volume_id: VolumeId) -> tuple[ChapterAggregate, ...]:
        if type(volume_id) is not VolumeId:
            raise InvalidNovelStructureState
        return self._read_many(
            lambda session: tuple(
                self._chapter_from_row(row)
                for row in session.execute(chapters_for_volume_query(volume_id)).all()
            )
        )

    def append_chapter_revision(
        self,
        chapter_id: ChapterId,
        *,
        expected_version: ConcurrencyVersion,
        title: NovelStructureTitle,
        summary: NovelStructureSummary,
        position: NovelStructurePosition,
        clock: Clock,
        revision_id_factory: Callable[[], ChapterRevisionId],
    ) -> ChapterAggregate:
        self._validate_append(
            chapter_id,
            ChapterId,
            expected_version,
            title,
            summary,
            clock,
            revision_id_factory,
            position,
        )
        session = self._new_session()
        try:
            self._begin_immediate(session)
            current = self._load_chapter(session, chapter_id)
            if current is None:
                raise ChapterNotFound
            assert_expected_version(current.chapter.concurrency_version, expected_version)
            if (
                session.scalar(
                    chapter_position_query(
                        current.chapter.volume_id,
                        int(position),
                        exclude_id=chapter_id,
                    )
                )
                is not None
            ):
                raise ChapterPositionConflict
            next_aggregate = append_chapter_revision(
                current,
                expected_version=expected_version,
                revision_id=revision_id_factory(),
                title=title,
                summary=summary,
                position=position,
                now=clock(),
            )
            session.add(chapter_revision_to_record(next_aggregate.current_revision))
            session.flush()
            self._move_chapter(session, current, next_aggregate)
            session.commit()
            return next_aggregate
        except DomainError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise NovelStructureRepositoryError from exc
        finally:
            session.close()

    def _new_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise NovelStructureRepositoryError from exc

    @staticmethod
    def _begin_immediate(session: Session) -> None:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")

    @staticmethod
    def _insert_three(session: Session, stable: object, revision: object, head: object) -> None:
        session.add(stable)
        session.flush()
        session.add(revision)
        session.flush()
        session.add(head)
        session.flush()

    def _read_one(self, loader: Callable[[Session], T]) -> T:
        session = self._new_session()
        try:
            value = loader(session)
            session.rollback()
            return value
        except NovelStructureDataCorruption:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise NovelStructureRepositoryError from exc
        finally:
            session.close()

    def _read_many(self, loader: Callable[[Session], T]) -> T:
        return self._read_one(loader)

    @staticmethod
    def _load_outline(session: Session, outline_id: OutlineId) -> OutlineAggregate | None:
        row = session.execute(current_outline_query(outline_id)).one_or_none()
        return None if row is None else SqlAlchemyNovelStructureRepository._outline_from_row(row)

    @staticmethod
    def _load_volume(session: Session, volume_id: VolumeId) -> VolumeAggregate | None:
        row = session.execute(current_volume_query(volume_id)).one_or_none()
        return None if row is None else SqlAlchemyNovelStructureRepository._volume_from_row(row)

    @staticmethod
    def _load_chapter(session: Session, chapter_id: ChapterId) -> ChapterAggregate | None:
        row = session.execute(current_chapter_query(chapter_id)).one_or_none()
        return None if row is None else SqlAlchemyNovelStructureRepository._chapter_from_row(row)

    @staticmethod
    def _outline_from_row(row: Any) -> OutlineAggregate:
        stable, project_id, head, revision = row
        if (
            project_id is None
            or project_id != stable.project_id
            or head is None
            or revision is None
        ):
            raise NovelStructureDataCorruption
        return outline_aggregate_from_records(stable, head, revision)

    @staticmethod
    def _volume_from_row(row: Any) -> VolumeAggregate:
        stable, project_id, head, revision = row
        if (
            project_id is None
            or project_id != stable.project_id
            or head is None
            or revision is None
        ):
            raise NovelStructureDataCorruption
        return volume_aggregate_from_records(stable, head, revision)

    @staticmethod
    def _chapter_from_row(row: Any) -> ChapterAggregate:
        stable, project_id, volume_project_id, head, revision = row
        if (
            project_id is None
            or volume_project_id is None
            or project_id != stable.project_id
            or volume_project_id != stable.project_id
            or head is None
            or revision is None
        ):
            raise NovelStructureDataCorruption
        return chapter_aggregate_from_records(stable, head, revision)

    @staticmethod
    def _validate_initial(
        aggregate: object,
        expected_type: type[OutlineAggregate] | type[VolumeAggregate] | type[ChapterAggregate],
        owner: str,
    ) -> None:
        if type(aggregate) is not expected_type:
            raise InvalidNovelStructureState
        typed = aggregate
        stable = getattr(typed, owner)
        if (
            stable.concurrency_version.value != 1
            or typed.current_revision.revision_number.value != 1
        ):
            raise InvalidNovelStructureState

    @staticmethod
    def _validate_append(
        stable_id: object,
        expected_id_type: type[object],
        expected_version: ConcurrencyVersion,
        title: NovelStructureTitle,
        summary: NovelStructureSummary,
        clock: Clock,
        revision_id_factory: Callable[[], object],
        position: NovelStructurePosition | None = None,
    ) -> None:
        if (
            type(stable_id) is not expected_id_type
            or type(expected_version) is not ConcurrencyVersion
            or type(title) is not NovelStructureTitle
            or type(summary) is not NovelStructureSummary
            or (position is not None and type(position) is not NovelStructurePosition)
            or not callable(clock)
            or not callable(revision_id_factory)
        ):
            raise InvalidNovelStructureState

    @staticmethod
    def _rowcount(result: object) -> None:
        if cast(CursorResult[Any], result).rowcount != 1:
            raise NovelStructureDataCorruption

    @classmethod
    def _move_outline(
        cls, session: Session, current: OutlineAggregate, next_aggregate: OutlineAggregate
    ) -> None:
        cls._rowcount(
            session.execute(
                stable_compare_and_swap(
                    OutlineRecord,
                    current.outline.id,
                    current.outline.concurrency_version,
                    next_aggregate.outline.concurrency_version,
                    next_aggregate.outline.updated_at,
                )
            )
        )
        cls._rowcount(
            session.execute(
                outline_head_compare_and_swap(
                    current.outline.id,
                    current.head.revision_id,
                    next_aggregate.head.revision_id,
                    next_aggregate.head.updated_at,
                )
            )
        )

    @classmethod
    def _move_volume(
        cls, session: Session, current: VolumeAggregate, next_aggregate: VolumeAggregate
    ) -> None:
        cls._rowcount(
            session.execute(
                stable_compare_and_swap(
                    VolumeRecord,
                    current.volume.id,
                    current.volume.concurrency_version,
                    next_aggregate.volume.concurrency_version,
                    next_aggregate.volume.updated_at,
                    current_position=int(next_aggregate.current_revision.position),
                )
            )
        )
        cls._rowcount(
            session.execute(
                volume_head_compare_and_swap(
                    current.volume.id,
                    current.head.revision_id,
                    next_aggregate.head.revision_id,
                    next_aggregate.head.updated_at,
                )
            )
        )

    @classmethod
    def _move_chapter(
        cls, session: Session, current: ChapterAggregate, next_aggregate: ChapterAggregate
    ) -> None:
        cls._rowcount(
            session.execute(
                stable_compare_and_swap(
                    ChapterRecord,
                    current.chapter.id,
                    current.chapter.concurrency_version,
                    next_aggregate.chapter.concurrency_version,
                    next_aggregate.chapter.updated_at,
                    current_position=int(next_aggregate.current_revision.position),
                )
            )
        )
        cls._rowcount(
            session.execute(
                chapter_head_compare_and_swap(
                    current.chapter.id,
                    current.head.revision_id,
                    next_aggregate.head.revision_id,
                    next_aggregate.head.updated_at,
                )
            )
        )


__all__ = ["SqlAlchemyNovelStructureRepository"]
