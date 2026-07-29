"""Character text value validation and privacy."""

from dataclasses import FrozenInstanceError

import pytest

from aiwebnovel.character import (
    CharacterName,
    CharacterProfile,
    CharacterRole,
    InvalidCharacterName,
    InvalidCharacterProfile,
    InvalidCharacterRole,
)

CANARY = "CHARACTER_SECRET_CANARY"


def test_character_name_normalizes_only_outer_unicode_whitespace() -> None:
    value = CharacterName(" \u3000叶  不 斩 \u3000")

    assert str(value) == "叶  不 斩"
    assert CharacterName("A").value == "A"
    assert CharacterName("😀").value == "😀"
    assert CharacterName("x" * 120).value == "x" * 120


@pytest.mark.parametrize(
    "value",
    [
        "",
        " \t\u3000",
        "x" * 121,
        "\t角色",
        "a\x00b",
        "a\x1fb",
        "a\x7fb",
        "a\x80b",
        "a\u2028b",
        "a\u2029b",
    ],
)
def test_character_name_rejects_invalid_text(value: str) -> None:
    with pytest.raises(InvalidCharacterName):
        CharacterName(value)


@pytest.mark.parametrize("value", [None, True, 1, b"name"])
def test_character_name_requires_exact_string(value: object) -> None:
    with pytest.raises(InvalidCharacterName):
        CharacterName(value)  # type: ignore[arg-type]


def test_character_role_is_free_text_and_empty_is_explicit() -> None:
    assert str(CharacterRole()) == ""
    assert str(CharacterRole(" \u3000主  角\u3000")) == "主  角"
    assert str(CharacterRole("Antagonist")) == "Antagonist"
    assert str(CharacterRole("😀" * 120)) == "😀" * 120


@pytest.mark.parametrize(
    "value",
    ["x" * 121, "\t主角", "a\x00b", "a\x7fb", "a\x85b", "a\u2028b", "a\u2029b"],
)
def test_character_role_rejects_invalid_text(value: str) -> None:
    with pytest.raises(InvalidCharacterRole):
        CharacterRole(value)


@pytest.mark.parametrize("value", [None, True, 1.0, b"role"])
def test_character_role_requires_exact_string(value: object) -> None:
    with pytest.raises(InvalidCharacterRole):
        CharacterRole(value)  # type: ignore[arg-type]


def test_character_profile_preserves_plain_text_and_normalizes_newlines() -> None:
    value = CharacterProfile("  第一行\r\n\t第二行\r第三行  ")

    assert str(value) == "  第一行\n\t第二行\n第三行  "
    assert CharacterProfile().value == ""
    assert CharacterProfile("😀" * 50_000).value == "😀" * 50_000


@pytest.mark.parametrize(
    "value",
    [
        "x" * 50_001,
        "a\x00b",
        "a\x01b",
        "a\x7fb",
        "a\x80b",
        "a\u2028b",
        "a\u2029b",
    ],
    ids=[
        "too-long",
        "nul",
        "c0",
        "del",
        "c1",
        "line-separator",
        "paragraph-separator",
    ],
)
def test_character_profile_rejects_invalid_text(value: str) -> None:
    with pytest.raises(InvalidCharacterProfile):
        CharacterProfile(value)


@pytest.mark.parametrize("value", [None, True, 1, b"profile"])
def test_character_profile_requires_exact_string(value: object) -> None:
    with pytest.raises(InvalidCharacterProfile):
        CharacterProfile(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("factory", "value", "error_type"),
    [
        (CharacterName, CANARY + "\x00", InvalidCharacterName),
        (CharacterRole, CANARY + "\x00", InvalidCharacterRole),
        (CharacterProfile, CANARY + "\x00", InvalidCharacterProfile),
    ],
)
def test_value_errors_never_disclose_character_text(
    factory: type,
    value: str,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type) as caught:
        factory(value)

    assert CANARY not in str(caught.value)
    assert CANARY not in repr(caught.value)


@pytest.mark.parametrize(
    "value",
    [CharacterName("角色"), CharacterRole("主角"), CharacterProfile("正文")],
)
def test_character_values_are_frozen_and_slotted(value: object) -> None:
    attribute = "value"
    with pytest.raises((FrozenInstanceError, AttributeError)):
        setattr(value, attribute, "changed")
    assert not hasattr(value, "__dict__")
