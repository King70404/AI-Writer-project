"""Story Bible title and content normalization boundary tests."""

import pytest

from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleContent,
    InvalidStoryBibleTitle,
)
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

CANARY = "STORY_BIBLE_SECRET_CANARY"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("设定", "设定"),
        ("  设定  ", "设定"),
        ("设  定", "设  定"),
        ("A", "A"),
        ("a", "a"),
        ("😀", "😀"),
    ],
)
def test_title_preserves_valid_unicode_and_only_strips_ends(
    raw: str,
    expected: str,
) -> None:
    title = StoryBibleTitle(raw)

    assert title.value == expected
    assert str(title) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " \t ",
        "标题\n第二行",
        "标题\x00",
        "标题\x7f",
        "标题\x85",
        "标题\u2028",
        "标题\u2029",
    ],
)
def test_title_rejects_empty_oversized_control_and_separator_input(raw: str) -> None:
    with pytest.raises(InvalidStoryBibleTitle) as caught:
        StoryBibleTitle(raw)

    if raw:
        assert raw not in str(caught.value)


def test_title_length_boundaries_count_unicode_code_points() -> None:
    assert StoryBibleTitle("界" * 120).value == "界" * 120

    with pytest.raises(InvalidStoryBibleTitle):
        StoryBibleTitle("界" * 121)


@pytest.mark.parametrize("raw", [None, 1, True, b"title"])
def test_title_rejects_non_strings(raw: object) -> None:
    with pytest.raises(InvalidStoryBibleTitle):
        StoryBibleTitle(raw)  # type: ignore[arg-type]


def test_title_error_does_not_leak_canary() -> None:
    with pytest.raises(InvalidStoryBibleTitle) as caught:
        StoryBibleTitle(f"{CANARY}\x00")

    assert CANARY not in str(caught.value)
    assert CANARY not in repr(caught.value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("第一行\n第二行", "第一行\n第二行"),
        ("第一行\r\n第二行", "第一行\n第二行"),
        ("第一行\r第二行", "第一行\n第二行"),
        ("\t设定\t", "\t设定\t"),
        ("  设定  ", "  设定  "),
        ("\n设定\n", "\n设定\n"),
        ("😀", "😀"),
    ],
)
def test_content_normalizes_only_line_endings(raw: str, expected: str) -> None:
    content = StoryBibleContent(raw)

    assert content.value == expected
    assert str(content) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "正文\x00",
        "正文\x01",
        "正文\x0b",
        "正文\x7f",
        "正文\x85",
        "正文\u2028",
        "正文\u2029",
    ],
)
def test_content_rejects_oversized_control_and_separator_input(raw: str) -> None:
    with pytest.raises(InvalidStoryBibleContent) as caught:
        StoryBibleContent(raw)

    assert raw not in str(caught.value)


def test_content_length_boundaries_count_unicode_code_points() -> None:
    valid = StoryBibleContent("界" * 50_000)
    assert len(valid.value) == 50_000

    with pytest.raises(InvalidStoryBibleContent):
        StoryBibleContent("界" * 50_001)


@pytest.mark.parametrize("raw", [None, 1, True, b"content"])
def test_content_rejects_non_strings(raw: object) -> None:
    with pytest.raises(InvalidStoryBibleContent):
        StoryBibleContent(raw)  # type: ignore[arg-type]


def test_content_error_does_not_leak_canary() -> None:
    with pytest.raises(InvalidStoryBibleContent) as caught:
        StoryBibleContent(f"{CANARY}\x00")

    assert CANARY not in str(caught.value)
    assert CANARY not in repr(caught.value)
