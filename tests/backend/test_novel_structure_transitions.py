"""Pure creation, ownership, revision, and concurrency transitions."""

from datetime import timedelta, timezone

import pytest
from tests.backend.novel_structure_support import (
    BASE_TIME,
    chapter_id,
    chapter_revision_id,
    initial_chapter,
    initial_outline,
    initial_volume,
    outline_id,
    outline_revision_id,
    project_id,
    volume_id,
    volume_revision_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.novel_structure import (
    InvalidNovelStructureState,
    ManuscriptContent,
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
    append_chapter_content_revision,
    append_chapter_revision,
    append_outline_revision,
    append_volume_revision,
    create_initial_chapter,
    create_initial_outline,
    create_initial_volume,
)


def test_initial_outline_uses_supplied_identity_content_and_time() -> None:
    aggregate = initial_outline()

    assert aggregate.outline.id == outline_id()
    assert aggregate.outline.project_id == project_id()
    assert aggregate.outline.created_at == BASE_TIME
    assert aggregate.outline.updated_at == BASE_TIME
    assert aggregate.current_revision.id == outline_revision_id()
    assert aggregate.current_revision.revision_number == RevisionNumber(1)
    assert str(aggregate.current_revision.title) == "总纲"
    assert str(aggregate.current_revision.summary) == "全书规划"


def test_initial_volume_uses_positive_position_and_revision_one() -> None:
    aggregate = initial_volume()

    assert aggregate.volume.id == volume_id()
    assert aggregate.volume.project_id == project_id()
    assert aggregate.current_revision.id == volume_revision_id()
    assert aggregate.current_revision.revision_number == RevisionNumber(1)
    assert int(aggregate.current_revision.position) == 1


def test_initial_chapter_inherits_exact_volume_and_project_ownership() -> None:
    aggregate = initial_chapter()
    volume = initial_volume().volume

    assert aggregate.chapter.id == chapter_id()
    assert aggregate.chapter.project_id == volume.project_id
    assert aggregate.chapter.volume_id == volume.id
    assert aggregate.current_revision.id == chapter_revision_id()
    assert aggregate.current_revision.revision_number == RevisionNumber(1)
    assert str(aggregate.current_revision.content) == ""
    assert not hasattr(aggregate.current_revision, "body")
    assert not hasattr(aggregate.current_revision, "draft")


def test_creation_normalizes_non_utc_aware_time() -> None:
    local_time = BASE_TIME.astimezone(timezone(timedelta(hours=8)))

    aggregate = create_initial_outline(
        outline_id=outline_id(),
        revision_id=outline_revision_id(),
        project_id=project_id(),
        title=NovelStructureTitle("总纲"),
        summary=NovelStructureSummary(),
        now=local_time,
    )

    assert aggregate.outline.created_at == BASE_TIME
    assert aggregate.current_revision.created_at == BASE_TIME


@pytest.mark.parametrize(
    "changes",
    [
        {"outline_id": volume_id()},
        {"revision_id": volume_revision_id()},
        {"project_id": volume_id()},
        {"title": NovelStructureSummary()},
        {"summary": NovelStructureTitle("wrong")},
        {"now": BASE_TIME.replace(tzinfo=None)},
    ],
)
def test_initial_outline_rejects_invalid_inputs(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "outline_id": outline_id(),
        "revision_id": outline_revision_id(),
        "project_id": project_id(),
        "title": NovelStructureTitle("总纲"),
        "summary": NovelStructureSummary(),
        "now": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidNovelStructureState):
        create_initial_outline(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"volume_id": outline_id()},
        {"revision_id": outline_revision_id()},
        {"project_id": volume_id()},
        {"title": NovelStructureSummary()},
        {"summary": NovelStructureTitle("wrong")},
        {"position": 1},
    ],
)
def test_initial_volume_rejects_invalid_inputs(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "volume_id": volume_id(),
        "revision_id": volume_revision_id(),
        "project_id": project_id(),
        "title": NovelStructureTitle("第一卷"),
        "summary": NovelStructureSummary(),
        "position": NovelStructurePosition(1),
        "now": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidNovelStructureState):
        create_initial_volume(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"chapter_id": volume_id()},
        {"revision_id": volume_revision_id()},
        {"project_id": volume_id()},
        {"volume": object()},
        {"title": NovelStructureSummary()},
        {"summary": NovelStructureTitle("wrong")},
        {"position": 1},
    ],
)
def test_initial_chapter_rejects_invalid_inputs(changes: dict[str, object]) -> None:
    volume = initial_volume().volume
    arguments: dict[str, object] = {
        "chapter_id": chapter_id(),
        "revision_id": chapter_revision_id(),
        "project_id": volume.project_id,
        "volume": volume,
        "title": NovelStructureTitle("第一章"),
        "summary": NovelStructureSummary(),
        "position": NovelStructurePosition(1),
        "now": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidNovelStructureState):
        create_initial_chapter(**arguments)  # type: ignore[arg-type]


def test_initial_chapter_rejects_cross_project_volume() -> None:
    volume = initial_volume().volume

    with pytest.raises(InvalidNovelStructureState):
        create_initial_chapter(
            chapter_id=chapter_id(),
            revision_id=chapter_revision_id(),
            project_id=project_id(30),
            volume=volume,
            title=NovelStructureTitle("第一章"),
            summary=NovelStructureSummary(),
            position=NovelStructurePosition(1),
            now=BASE_TIME,
        )


def test_appends_are_complete_replacements_and_strictly_increment() -> None:
    old_outline = initial_outline()
    new_outline = append_outline_revision(
        old_outline,
        expected_version=ConcurrencyVersion(1),
        revision_id=outline_revision_id(30),
        title=NovelStructureTitle("新总纲"),
        summary=NovelStructureSummary(""),
        now=BASE_TIME + timedelta(seconds=1),
    )
    old_volume = initial_volume()
    new_volume = append_volume_revision(
        old_volume,
        expected_version=ConcurrencyVersion(1),
        revision_id=volume_revision_id(30),
        title=NovelStructureTitle("新卷"),
        summary=NovelStructureSummary(""),
        position=NovelStructurePosition(2),
        now=BASE_TIME + timedelta(seconds=1),
    )
    old_chapter = initial_chapter()
    new_chapter = append_chapter_revision(
        old_chapter,
        expected_version=ConcurrencyVersion(1),
        revision_id=chapter_revision_id(30),
        title=NovelStructureTitle("新章"),
        summary=NovelStructureSummary(""),
        position=NovelStructurePosition(2),
        now=BASE_TIME + timedelta(seconds=1),
    )

    for old, new in (
        (old_outline, new_outline),
        (old_volume, new_volume),
        (old_chapter, new_chapter),
    ):
        assert old.current_revision.revision_number == RevisionNumber(1)
        assert new.current_revision.revision_number == RevisionNumber(2)
        assert new.current_revision.created_at > old.current_revision.created_at
        assert str(new.current_revision.summary) == ""
    assert new_outline.outline.concurrency_version == ConcurrencyVersion(2)
    assert new_volume.volume.concurrency_version == ConcurrencyVersion(2)
    assert new_chapter.chapter.concurrency_version == ConcurrencyVersion(2)
    assert int(new_volume.current_revision.position) == 2
    assert int(new_chapter.current_revision.position) == 2
    assert old_chapter.chapter.volume_id == new_chapter.chapter.volume_id


def test_chapter_structure_and_content_transitions_preserve_the_other_fields() -> None:
    initial = initial_chapter()
    written = append_chapter_content_revision(
        initial,
        expected_version=ConcurrencyVersion(1),
        revision_id=chapter_revision_id(31),
        content=ManuscriptContent("first\r\ndraft"),
        now=BASE_TIME + timedelta(seconds=1),
    )
    structured = append_chapter_revision(
        written,
        expected_version=ConcurrencyVersion(2),
        revision_id=chapter_revision_id(32),
        title=NovelStructureTitle("新标题"),
        summary=NovelStructureSummary("新摘要"),
        position=NovelStructurePosition(2),
        now=BASE_TIME + timedelta(seconds=2),
    )
    rewritten = append_chapter_content_revision(
        structured,
        expected_version=ConcurrencyVersion(3),
        revision_id=chapter_revision_id(33),
        content=ManuscriptContent("second draft"),
        now=BASE_TIME + timedelta(seconds=3),
    )

    assert str(written.current_revision.content) == "first\ndraft"
    assert str(structured.current_revision.content) == "first\ndraft"
    assert structured.current_revision.title == NovelStructureTitle("新标题")
    assert rewritten.current_revision.title == structured.current_revision.title
    assert rewritten.current_revision.summary == structured.current_revision.summary
    assert rewritten.current_revision.position == structured.current_revision.position
    assert str(rewritten.current_revision.content) == "second draft"
    assert rewritten.current_revision.revision_number == RevisionNumber(4)
    assert rewritten.chapter.concurrency_version == ConcurrencyVersion(4)


def test_chapter_content_transition_rejects_stale_and_invalid_inputs() -> None:
    initial = initial_chapter()
    with pytest.raises(ConcurrencyConflict):
        append_chapter_content_revision(
            initial,
            expected_version=ConcurrencyVersion(2),
            revision_id=chapter_revision_id(31),
            content=ManuscriptContent("draft"),
            now=BASE_TIME + timedelta(seconds=1),
        )
    with pytest.raises(InvalidNovelStructureState):
        append_chapter_content_revision(  # type: ignore[arg-type]
            object(),
            expected_version=ConcurrencyVersion(1),
            revision_id=chapter_revision_id(31),
            content=ManuscriptContent("draft"),
            now=BASE_TIME + timedelta(seconds=1),
        )
    with pytest.raises(InvalidNovelStructureState):
        append_chapter_content_revision(
            initial,
            expected_version=ConcurrencyVersion(1),
            revision_id=chapter_revision_id(31),
            content="draft",  # type: ignore[arg-type]
            now=BASE_TIME + timedelta(seconds=1),
        )


@pytest.mark.parametrize(
    ("append", "aggregate", "arguments"),
    [
        (
            append_outline_revision,
            initial_outline(),
            {
                "revision_id": outline_revision_id(30),
                "title": NovelStructureTitle("总纲"),
                "summary": NovelStructureSummary(),
            },
        ),
        (
            append_volume_revision,
            initial_volume(),
            {
                "revision_id": volume_revision_id(30),
                "title": NovelStructureTitle("卷"),
                "summary": NovelStructureSummary(),
                "position": NovelStructurePosition(1),
            },
        ),
        (
            append_chapter_revision,
            initial_chapter(),
            {
                "revision_id": chapter_revision_id(30),
                "title": NovelStructureTitle("章"),
                "summary": NovelStructureSummary(),
                "position": NovelStructurePosition(1),
            },
        ),
    ],
)
def test_stale_revision_conflicts_preserve_expected_and_actual(
    append: object,
    aggregate: object,
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ConcurrencyConflict) as caught:
        append(  # type: ignore[operator]
            aggregate,
            expected_version=ConcurrencyVersion(2),
            now=BASE_TIME,
            **arguments,
        )

    assert caught.value.expected_version == 2
    assert caught.value.actual_version == 1


@pytest.mark.parametrize(
    ("append", "aggregate", "arguments"),
    [
        (
            append_outline_revision,
            initial_outline(),
            {
                "revision_id": volume_revision_id(),
                "title": NovelStructureTitle("总纲"),
                "summary": NovelStructureSummary(),
            },
        ),
        (
            append_volume_revision,
            initial_volume(),
            {
                "revision_id": outline_revision_id(),
                "title": NovelStructureTitle("卷"),
                "summary": NovelStructureSummary(),
                "position": NovelStructurePosition(1),
            },
        ),
        (
            append_chapter_revision,
            initial_chapter(),
            {
                "revision_id": volume_revision_id(),
                "title": NovelStructureTitle("章"),
                "summary": NovelStructureSummary(),
                "position": NovelStructurePosition(1),
            },
        ),
    ],
)
def test_appends_reject_wrong_revision_identity(
    append: object,
    aggregate: object,
    arguments: dict[str, object],
) -> None:
    with pytest.raises(InvalidNovelStructureState):
        append(  # type: ignore[operator]
            aggregate,
            expected_version=ConcurrencyVersion(1),
            now=BASE_TIME,
            **arguments,
        )


def test_appends_reject_wrong_aggregate_type() -> None:
    with pytest.raises(InvalidNovelStructureState):
        append_outline_revision(  # type: ignore[arg-type]
            object(),
            expected_version=ConcurrencyVersion(1),
            revision_id=outline_revision_id(30),
            title=NovelStructureTitle("总纲"),
            summary=NovelStructureSummary(),
            now=BASE_TIME,
        )
    with pytest.raises(InvalidNovelStructureState):
        append_volume_revision(  # type: ignore[arg-type]
            object(),
            expected_version=ConcurrencyVersion(1),
            revision_id=volume_revision_id(30),
            title=NovelStructureTitle("卷"),
            summary=NovelStructureSummary(),
            position=NovelStructurePosition(1),
            now=BASE_TIME,
        )
    with pytest.raises(InvalidNovelStructureState):
        append_chapter_revision(  # type: ignore[arg-type]
            object(),
            expected_version=ConcurrencyVersion(1),
            revision_id=chapter_revision_id(30),
            title=NovelStructureTitle("章"),
            summary=NovelStructureSummary(),
            position=NovelStructurePosition(1),
            now=BASE_TIME,
        )


def test_appends_reject_time_rollback_and_reused_revision_ids() -> None:
    outline = initial_outline()
    volume = initial_volume()
    chapter = initial_chapter()

    with pytest.raises(InvalidNovelStructureState):
        append_outline_revision(
            outline,
            expected_version=ConcurrencyVersion(1),
            revision_id=outline_revision_id(30),
            title=NovelStructureTitle("总纲"),
            summary=NovelStructureSummary(),
            now=BASE_TIME - timedelta(microseconds=1),
        )
    with pytest.raises(InvalidNovelStructureState):
        append_volume_revision(
            volume,
            expected_version=ConcurrencyVersion(1),
            revision_id=volume.current_revision.id,
            title=NovelStructureTitle("卷"),
            summary=NovelStructureSummary(),
            position=NovelStructurePosition(1),
            now=BASE_TIME,
        )
    with pytest.raises(InvalidNovelStructureState):
        append_chapter_revision(
            chapter,
            expected_version=ConcurrencyVersion(1),
            revision_id=chapter.current_revision.id,
            title=NovelStructureTitle("章"),
            summary=NovelStructureSummary(),
            position=NovelStructurePosition(1),
            now=BASE_TIME,
        )
