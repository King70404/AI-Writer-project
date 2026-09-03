"""Novel-structure title, summary, and position rules."""

from dataclasses import FrozenInstanceError

import pytest

from aiwebnovel.domain.errors import InvalidRevisionNumber
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.novel_structure import (
    MAX_MANUSCRIPT_CONTENT_LENGTH,
    MAX_NOVEL_STRUCTURE_POSITION,
    MAX_NOVEL_STRUCTURE_SUMMARY_LENGTH,
    MAX_NOVEL_STRUCTURE_TITLE_LENGTH,
    InvalidManuscriptContent,
    InvalidNovelStructurePosition,
    InvalidNovelStructureSummary,
    InvalidNovelStructureTitle,
    ManuscriptContent,
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)


def test_title_is_trimmed_and_bounded() -> None:
    title = NovelStructureTitle("  第一卷  ")

    assert str(title) == "第一卷"
    assert str(NovelStructureTitle("题" * MAX_NOVEL_STRUCTURE_TITLE_LENGTH))


@pytest.mark.parametrize(
    "value",
    ["", " ", "题" * (MAX_NOVEL_STRUCTURE_TITLE_LENGTH + 1), "题\n目", "题\u2028目", None],
)
def test_title_rejects_invalid_values_without_leaking_them(value: object) -> None:
    with pytest.raises(InvalidNovelStructureTitle) as caught:
        NovelStructureTitle(value)  # type: ignore[arg-type]

    assert "题" not in str(caught.value)


def test_summary_allows_empty_and_normalizes_line_endings() -> None:
    assert str(NovelStructureSummary()) == ""
    assert str(NovelStructureSummary("甲\r\n乙\r丙\n\t丁")) == "甲\n乙\n丙\n\t丁"
    assert len(str(NovelStructureSummary("摘" * MAX_NOVEL_STRUCTURE_SUMMARY_LENGTH))) == 2_000


@pytest.mark.parametrize(
    "value",
    ["摘" * (MAX_NOVEL_STRUCTURE_SUMMARY_LENGTH + 1), "摘要\x00", "摘要\u2029", None],
)
def test_summary_rejects_invalid_values(value: object) -> None:
    with pytest.raises(InvalidNovelStructureSummary):
        NovelStructureSummary(value)  # type: ignore[arg-type]


def test_manuscript_allows_long_plain_text_and_normalizes_line_endings() -> None:
    assert str(ManuscriptContent()) == ""
    assert str(ManuscriptContent("甲\r\n乙\r丙\n\t丁")) == "甲\n乙\n丙\n\t丁"
    assert len(str(ManuscriptContent("文" * MAX_MANUSCRIPT_CONTENT_LENGTH))) == 2_000_000


@pytest.mark.parametrize(
    "value",
    [
        "文" * (MAX_MANUSCRIPT_CONTENT_LENGTH + 1),
        "STORY_CONTENT_SECRET_CANARY\x00",
        "正文\u2028分隔",
        "正文\u2029分隔",
        None,
    ],
    ids=["too-long", "control-canary", "line-separator", "paragraph-separator", "non-string"],
)
def test_manuscript_rejects_invalid_values_without_leaking_content(value: object) -> None:
    with pytest.raises(InvalidManuscriptContent) as caught:
        ManuscriptContent(value)  # type: ignore[arg-type]
    assert "STORY_CONTENT_SECRET_CANARY" not in str(caught.value)


@pytest.mark.parametrize("value", [1, 2, MAX_NOVEL_STRUCTURE_POSITION])
def test_position_accepts_positive_signed_64_bit_integers(value: int) -> None:
    assert int(NovelStructurePosition(value)) == value


@pytest.mark.parametrize(
    "value",
    [0, -1, MAX_NOVEL_STRUCTURE_POSITION + 1, True, 1.0, "1", None],
)
def test_position_rejects_non_positive_non_integer_or_overflow(value: object) -> None:
    with pytest.raises(InvalidNovelStructurePosition):
        NovelStructurePosition(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, -1, True, 1.0])
def test_revision_number_rejects_non_positive_or_non_integer_values(value: object) -> None:
    with pytest.raises(InvalidRevisionNumber):
        RevisionNumber(value)  # type: ignore[arg-type]


def test_values_are_frozen_slots_objects() -> None:
    values = [
        ManuscriptContent(),
        NovelStructureTitle("标题"),
        NovelStructureSummary(),
        NovelStructurePosition(1),
    ]

    assert all(not hasattr(value, "__dict__") for value in values)
    for value in values:
        with pytest.raises((FrozenInstanceError, AttributeError)):
            value.value = object()  # type: ignore[misc]
