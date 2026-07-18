"""Tests for immutable Project title and description values."""

from dataclasses import FrozenInstanceError

import pytest

from aiwebnovel.project.errors import InvalidProjectDescription, InvalidProjectTitle
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.unit


def test_project_title_normalizes_edges_and_preserves_internal_text() -> None:
    title = ProjectTitle("  我的  Novel  ")

    assert str(title) == "我的  Novel"
    assert title.value == "我的  Novel"
    assert ProjectTitle("Mixed CASE") != ProjectTitle("mixed case")


def test_project_title_accepts_unicode_boundaries_and_hashes() -> None:
    one = ProjectTitle("书")
    maximum = ProjectTitle("界" * 120)

    assert len(str(one)) == 1
    assert len(str(maximum)) == 120
    assert {one: "title"}[ProjectTitle("书")] == "title"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "x" * 121,
        "bad\x00title",
        "bad\ntitle",
        "bad\rtitle",
        "bad\ttitle",
        "bad\x7f",
        "bad\x85",
        "bad\u2028title",
        "bad\u2029title",
    ],
)
def test_project_title_rejects_empty_long_or_control_text_without_echo(value: str) -> None:
    with pytest.raises(InvalidProjectTitle) as captured:
        ProjectTitle(value)

    assert str(captured.value) == "The Project title is invalid."
    if value:
        assert value not in str(captured.value)


@pytest.mark.parametrize("value", [None, 12, 1.5, True, ["title"]])
def test_project_title_rejects_non_strings(value: object) -> None:
    with pytest.raises(InvalidProjectTitle):
        ProjectTitle(value)


def test_project_title_is_immutable() -> None:
    title = ProjectTitle("Stable")

    with pytest.raises(FrozenInstanceError):
        title.value = "Changed"

    assert str(title) == "Stable"


def test_project_description_allows_empty_multiline_tabs_and_normalizes_newlines() -> None:
    empty = ProjectDescription()
    description = ProjectDescription("first\r\nsecond\rthird\n\tfourth")

    assert str(empty) == ""
    assert str(description) == "first\nsecond\nthird\n\tfourth"
    assert "\r" not in description.value


def test_project_description_accepts_maximum_length_and_hashes() -> None:
    description = ProjectDescription("介" * 2_000)

    assert len(str(description)) == 2_000
    assert {description: "description"}[ProjectDescription("介" * 2_000)] == "description"


@pytest.mark.parametrize(
    "value",
    ["x" * 2_001, "bad\x00description", "bad\x01description", "bad\x7f", "bad\x85"],
)
def test_project_description_rejects_long_or_forbidden_control_text(value: str) -> None:
    with pytest.raises(InvalidProjectDescription) as captured:
        ProjectDescription(value)

    assert str(captured.value) == "The Project description is invalid."
    assert value not in str(captured.value)


@pytest.mark.parametrize("value", [None, 12, 1.5, True, ["description"]])
def test_project_description_rejects_non_strings(value: object) -> None:
    with pytest.raises(InvalidProjectDescription):
        ProjectDescription(value)


def test_project_description_is_immutable() -> None:
    description = ProjectDescription("Stable")

    with pytest.raises(FrozenInstanceError):
        description.value = "Changed"

    assert str(description) == "Stable"
