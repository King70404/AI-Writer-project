"""Transactional repository behavior for Outline, Volume, and Chapter."""

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.backend.novel_structure_repository_support import (
    chapter_aggregate,
    chapter_revision_id,
    create_project,
    later,
    outline_aggregate,
    outline_revision_id,
    repository_database,
    volume_aggregate,
    volume_revision_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.novel_structure import (
    ChapterNotFound,
    ChapterPositionConflict,
    ChapterVolumeOwnershipMismatch,
    InvalidNovelStructureState,
    ManuscriptContent,
    NovelStructurePosition,
    NovelStructureProjectNotFound,
    NovelStructureRepositoryError,
    NovelStructureSummary,
    NovelStructureTitle,
    OutlineAlreadyExists,
    VolumePositionConflict,
)

pytestmark = pytest.mark.integration


def test_outline_create_read_by_id_and_project_and_append(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        initial = outline_aggregate()
        assert database.repository.create_outline(initial) == initial
        assert database.repository.get_outline(initial.outline.id) == initial
        assert database.repository.get_outline_for_project(initial.outline.project_id) == initial

        revised = database.repository.append_outline_revision(
            initial.outline.id,
            expected_version=ConcurrencyVersion(1),
            title=NovelStructureTitle("Revised outline"),
            summary=NovelStructureSummary("Revised summary"),
            clock=lambda: later(),
            revision_id_factory=lambda: outline_revision_id(20_101),
        )
        with database.engine.connect() as connection:
            counts = (
                connection.exec_driver_sql("SELECT COUNT(*) FROM outlines").scalar_one(),
                connection.exec_driver_sql("SELECT COUNT(*) FROM outline_revisions").scalar_one(),
                connection.exec_driver_sql("SELECT COUNT(*) FROM outline_heads").scalar_one(),
            )

    assert revised.outline.concurrency_version == ConcurrencyVersion(2)
    assert str(revised.current_revision.title) == "Revised outline"
    assert counts == (1, 2, 1)


def test_outline_rejects_missing_project_second_project_outline_and_stale(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        with pytest.raises(NovelStructureProjectNotFound):
            database.repository.create_outline(outline_aggregate())
        create_project(database)
        initial = outline_aggregate()
        database.repository.create_outline(initial)
        with pytest.raises(OutlineAlreadyExists):
            database.repository.create_outline(outline_aggregate(2))
        database.repository.append_outline_revision(
            initial.outline.id,
            expected_version=ConcurrencyVersion(1),
            title=NovelStructureTitle("Revision 2"),
            summary=NovelStructureSummary(),
            clock=lambda: later(),
            revision_id_factory=lambda: outline_revision_id(20_102),
        )
        with pytest.raises(ConcurrencyConflict) as caught:
            database.repository.append_outline_revision(
                initial.outline.id,
                expected_version=ConcurrencyVersion(1),
                title=NovelStructureTitle("Stale"),
                summary=NovelStructureSummary(),
                clock=lambda: later(2),
                revision_id_factory=lambda: outline_revision_id(20_103),
            )

    assert caught.value.expected_version == 1
    assert caught.value.actual_version == 2


def test_volume_order_current_uniqueness_history_and_stale(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        first = volume_aggregate(1, position=1)
        database.repository.create_volume(first)
        revised = database.repository.append_volume_revision(
            first.volume.id,
            expected_version=ConcurrencyVersion(1),
            title=NovelStructureTitle("Moved volume"),
            summary=NovelStructureSummary(),
            position=NovelStructurePosition(2),
            clock=lambda: later(),
            revision_id_factory=lambda: volume_revision_id(20_201),
        )
        second = volume_aggregate(2, position=1)
        database.repository.create_volume(second)
        ordered = database.repository.list_volumes_for_project(first.volume.project_id)
        with pytest.raises(VolumePositionConflict):
            database.repository.create_volume(volume_aggregate(3, position=1))
        with pytest.raises(VolumePositionConflict):
            database.repository.append_volume_revision(
                first.volume.id,
                expected_version=ConcurrencyVersion(2),
                title=NovelStructureTitle("Conflict"),
                summary=NovelStructureSummary(),
                position=NovelStructurePosition(1),
                clock=lambda: later(2),
                revision_id_factory=lambda: volume_revision_id(20_202),
            )
        with pytest.raises(ConcurrencyConflict):
            database.repository.append_volume_revision(
                first.volume.id,
                expected_version=ConcurrencyVersion(1),
                title=NovelStructureTitle("Stale"),
                summary=NovelStructureSummary(),
                position=NovelStructurePosition(3),
                clock=lambda: later(2),
                revision_id_factory=lambda: volume_revision_id(20_203),
            )
        with database.engine.connect() as connection:
            history = (
                connection.exec_driver_sql(
                    "SELECT position FROM volume_revisions ORDER BY volume_id, revision_number"
                )
                .scalars()
                .all()
            )

    assert revised.current_revision.position == NovelStructurePosition(2)
    assert [item.volume.id for item in ordered] == [second.volume.id, first.volume.id]
    assert history.count(1) == 2


def test_chapter_order_current_uniqueness_history_owner_and_stale(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        create_project(database, 1)
        create_project(database, 2)
        volume = volume_aggregate(1, project_value=1, position=1)
        database.repository.create_volume(volume)
        first = chapter_aggregate(volume, 1, position=1)
        database.repository.create_chapter(first)
        revised = database.repository.append_chapter_revision(
            first.chapter.id,
            expected_version=ConcurrencyVersion(1),
            title=NovelStructureTitle("Moved chapter"),
            summary=NovelStructureSummary(),
            position=NovelStructurePosition(2),
            clock=lambda: later(),
            revision_id_factory=lambda: chapter_revision_id(20_301),
        )
        second = chapter_aggregate(volume, 2, position=1)
        database.repository.create_chapter(second)
        ordered = database.repository.list_chapters_for_volume(volume.volume.id)
        with pytest.raises(ChapterPositionConflict):
            database.repository.create_chapter(chapter_aggregate(volume, 3, position=1))
        with pytest.raises(ChapterPositionConflict):
            database.repository.append_chapter_revision(
                first.chapter.id,
                expected_version=ConcurrencyVersion(2),
                title=NovelStructureTitle("Conflict"),
                summary=NovelStructureSummary(),
                position=NovelStructurePosition(1),
                clock=lambda: later(2),
                revision_id_factory=lambda: chapter_revision_id(20_302),
            )
        with pytest.raises(ConcurrencyConflict):
            database.repository.append_chapter_revision(
                first.chapter.id,
                expected_version=ConcurrencyVersion(1),
                title=NovelStructureTitle("Stale"),
                summary=NovelStructureSummary(),
                position=NovelStructurePosition(3),
                clock=lambda: later(2),
                revision_id_factory=lambda: chapter_revision_id(20_303),
            )
        with pytest.raises(ChapterVolumeOwnershipMismatch):
            database.repository.create_chapter(
                chapter_aggregate(volume, 4, project_value=2, position=3)
            )
        with database.engine.connect() as connection:
            history = (
                connection.exec_driver_sql(
                    "SELECT position FROM chapter_revisions ORDER BY chapter_id, revision_number"
                )
                .scalars()
                .all()
            )

    assert revised.current_revision.position == NovelStructurePosition(2)
    assert [item.chapter.id for item in ordered] == [second.chapter.id, first.chapter.id]
    assert history.count(1) == 2


def test_chapter_content_and_structure_updates_share_one_immutable_revision_sequence(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        volume = volume_aggregate()
        database.repository.create_volume(volume)
        chapter = chapter_aggregate(volume, position=2)
        database.repository.create_chapter(chapter)
        written = database.repository.append_chapter_content_revision(
            chapter.chapter.id,
            expected_version=ConcurrencyVersion(1),
            content=ManuscriptContent("正文一\r\n第二行"),
            clock=lambda: later(1),
            revision_id_factory=lambda: chapter_revision_id(20_311),
        )
        structured = database.repository.append_chapter_revision(
            chapter.chapter.id,
            expected_version=ConcurrencyVersion(2),
            title=NovelStructureTitle("Revised structure"),
            summary=NovelStructureSummary("Revised summary"),
            position=NovelStructurePosition(3),
            clock=lambda: later(2),
            revision_id_factory=lambda: chapter_revision_id(20_312),
        )
        rewritten = database.repository.append_chapter_content_revision(
            chapter.chapter.id,
            expected_version=ConcurrencyVersion(3),
            content=ManuscriptContent("正文二"),
            clock=lambda: later(3),
            revision_id_factory=lambda: chapter_revision_id(20_313),
        )
        current = database.repository.get_chapter(chapter.chapter.id)
        with database.engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT revision_number, title, summary, position, content "
                "FROM chapter_revisions ORDER BY revision_number"
            ).all()
            head = connection.exec_driver_sql(
                "SELECT revision_id FROM chapter_heads WHERE chapter_id = ?",
                (str(chapter.chapter.id),),
            ).scalar_one()

    assert str(written.current_revision.content) == "正文一\n第二行"
    assert str(structured.current_revision.content) == "正文一\n第二行"
    assert rewritten.current_revision.title == structured.current_revision.title
    assert rewritten.current_revision.summary == structured.current_revision.summary
    assert rewritten.current_revision.position == structured.current_revision.position
    assert current == rewritten
    assert rows == [
        (1, "Chapter 1", "Chapter summary 1", 2, ""),
        (2, "Chapter 1", "Chapter summary 1", 2, "正文一\n第二行"),
        (3, "Revised structure", "Revised summary", 3, "正文一\n第二行"),
        (4, "Revised structure", "Revised summary", 3, "正文二"),
    ]
    assert head == str(rewritten.current_revision.id)


@pytest.mark.parametrize(
    "changes",
    [
        {"chapter_id": object()},
        {"expected_version": object()},
        {"content": "not-a-value"},
        {"clock": object()},
        {"revision_id_factory": object()},
    ],
)
def test_chapter_content_append_rejects_invalid_dependencies_without_opening_session(
    tmp_path: Path,
    changes: dict[str, object],
) -> None:
    with repository_database(tmp_path) as database:
        arguments: dict[str, object] = {
            "chapter_id": chapter_aggregate(volume_aggregate()).chapter.id,
            "expected_version": ConcurrencyVersion(1),
            "content": ManuscriptContent("draft"),
            "clock": lambda: later(),
            "revision_id_factory": lambda: chapter_revision_id(20_320),
        }
        arguments.update(changes)
        with pytest.raises(InvalidNovelStructureState):
            database.repository.append_chapter_content_revision(**arguments)  # type: ignore[arg-type]


def test_chapter_content_append_maps_missing_and_unexpected_persistence_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with repository_database(tmp_path) as database:
        with pytest.raises(ChapterNotFound):
            database.repository.append_chapter_content_revision(
                chapter_aggregate(volume_aggregate()).chapter.id,
                expected_version=ConcurrencyVersion(1),
                content=ManuscriptContent("draft"),
                clock=lambda: later(),
                revision_id_factory=lambda: chapter_revision_id(20_321),
            )

        create_project(database)
        volume = volume_aggregate()
        database.repository.create_volume(volume)
        chapter = chapter_aggregate(volume)
        database.repository.create_chapter(chapter)
        monkeypatch.setattr(
            "aiwebnovel.novel_structure.persistence.repository.chapter_revision_to_record",
            lambda _revision: (_ for _ in ()).throw(RuntimeError("opaque")),
        )
        with pytest.raises(NovelStructureRepositoryError) as caught:
            database.repository.append_chapter_content_revision(
                chapter.chapter.id,
                expected_version=ConcurrencyVersion(1),
                content=ManuscriptContent("STORY_CONTENT_SECRET_CANARY"),
                clock=lambda: later(),
                revision_id_factory=lambda: chapter_revision_id(20_322),
            )
        assert "STORY_CONTENT_SECRET_CANARY" not in str(caught.value)


def test_failed_mid_create_rolls_back_stable_revision_and_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)

        def fail_after_stable(
            session: Session,
            stable: object,
            _revision: object,
            _head: object,
        ) -> None:
            session.add(stable)
            session.flush()
            raise RuntimeError("controlled failure")

        monkeypatch.setattr(database.repository, "_insert_three", fail_after_stable)
        with pytest.raises(NovelStructureRepositoryError):
            database.repository.create_outline(outline_aggregate())
        with database.engine.connect() as connection:
            counts = tuple(
                connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
                for table in ("outlines", "outline_revisions", "outline_heads")
            )

    assert counts == (0, 0, 0)


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("outline_revisions", "summary"),
        ("volume_revisions", "summary"),
        ("chapter_revisions", "summary"),
    ],
)
def test_all_new_revision_tables_reject_update_and_delete(
    tmp_path: Path,
    table: str,
    column: str,
) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        outline = outline_aggregate()
        volume = volume_aggregate()
        chapter = chapter_aggregate(volume)
        database.repository.create_outline(outline)
        database.repository.create_volume(volume)
        database.repository.create_chapter(chapter)
        with database.engine.begin() as connection, pytest.raises(IntegrityError):
            connection.exec_driver_sql(f"UPDATE {table} SET {column} = 'changed'")
        with database.engine.begin() as connection, pytest.raises(IntegrityError):
            connection.exec_driver_sql(f"DELETE FROM {table}")
