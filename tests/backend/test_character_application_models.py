"""Strict CharacterSnapshot, list item, and page invariants."""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta

import pytest
from tests.backend.character_repository_support import (
    BASE_TIME,
    character_id,
    character_revision_id,
    project_id,
)

from aiwebnovel.character.application.models import (
    CharacterListItem,
    CharacterListPage,
    CharacterListPosition,
    CharacterSnapshot,
)
from aiwebnovel.character.errors import (
    InvalidCharacterName,
    InvalidCharacterProfile,
    InvalidCharacterRole,
)
from aiwebnovel.domain.errors import (
    InvalidConcurrencyVersion,
    InvalidDomainIdentifier,
    InvalidRevisionNumber,
)

CANARY = "CHARACTER_APPLICATION_SECRET_CANARY"


def snapshot_values() -> dict[str, object]:
    return {
        "character_id": str(character_id(1)),
        "project_id": str(project_id(1)),
        "current_revision_id": str(character_revision_id(20_001)),
        "revision_number": 1,
        "concurrency_version": 1,
        "name": "  Name  ",
        "role": "  Role  ",
        "profile": "line one\r\nline two\r",
        "created_at": BASE_TIME,
        "updated_at": BASE_TIME,
        "revision_created_at": BASE_TIME,
        "head_updated_at": BASE_TIME,
    }


def make_snapshot(**changes: object) -> CharacterSnapshot:
    values = snapshot_values()
    values.update(changes)
    return CharacterSnapshot(**values)  # type: ignore[arg-type]


def list_item(
    value: int = 1,
    *,
    created_at: datetime = BASE_TIME,
    updated_at: datetime = BASE_TIME,
) -> CharacterListItem:
    return CharacterListItem(
        character_id=str(character_id(value)),
        current_revision_id=str(character_revision_id(20_000 + value)),
        revision_number=1,
        concurrency_version=1,
        name=f"Name {value}",
        role="Role",
        created_at=created_at,
        updated_at=updated_at,
    )


def test_snapshot_has_exact_fields_normalizes_text_and_is_frozen() -> None:
    snapshot = make_snapshot()

    assert tuple(field.name for field in fields(snapshot)) == (
        "character_id",
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "name",
        "role",
        "profile",
        "created_at",
        "updated_at",
        "revision_created_at",
        "head_updated_at",
    )
    assert (snapshot.name, snapshot.role, snapshot.profile) == (
        "Name",
        "Role",
        "line one\nline two\n",
    )
    assert not hasattr(snapshot, "__dict__")
    with pytest.raises(FrozenInstanceError):
        snapshot.name = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"character_id": 1}, TypeError),
        ({"character_id": "invalid"}, InvalidDomainIdentifier),
        ({"project_id": 1}, TypeError),
        ({"project_id": "invalid"}, InvalidDomainIdentifier),
        ({"current_revision_id": 1}, TypeError),
        ({"current_revision_id": "invalid"}, InvalidDomainIdentifier),
        ({"revision_number": True}, TypeError),
        ({"revision_number": 0}, InvalidRevisionNumber),
        ({"concurrency_version": True}, TypeError),
        ({"concurrency_version": 0}, InvalidConcurrencyVersion),
        ({"revision_number": 2}, ValueError),
        ({"name": 1}, TypeError),
        ({"name": " "}, InvalidCharacterName),
        ({"role": 1}, TypeError),
        ({"role": "\x00"}, InvalidCharacterRole),
        ({"profile": 1}, TypeError),
        ({"profile": "\x00"}, InvalidCharacterProfile),
        ({"created_at": "bad"}, TypeError),
        ({"created_at": datetime(2026, 1, 1)}, ValueError),
        ({"created_at": BASE_TIME + timedelta(seconds=1)}, ValueError),
        ({"revision_created_at": BASE_TIME + timedelta(seconds=1)}, ValueError),
        ({"head_updated_at": BASE_TIME + timedelta(seconds=1)}, ValueError),
    ],
)
def test_snapshot_rejects_invalid_primitive_or_invariant(
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        make_snapshot(**changes)


def test_snapshot_errors_do_not_echo_character_card() -> None:
    for changes in (
        {"name": f"\x00{CANARY}"},
        {"role": f"\x00{CANARY}"},
        {"profile": f"\x00{CANARY}"},
    ):
        with pytest.raises(Exception) as captured:
            make_snapshot(**changes)
        assert CANARY not in str(captured.value)


def test_list_item_has_exact_fields_omits_profile_and_is_frozen() -> None:
    item = list_item()

    assert tuple(field.name for field in fields(item)) == (
        "character_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "name",
        "role",
        "created_at",
        "updated_at",
    )
    assert not hasattr(item, "profile")
    with pytest.raises(FrozenInstanceError):
        item.role = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("character_id", "bad", InvalidDomainIdentifier),
        ("current_revision_id", "bad", InvalidDomainIdentifier),
        ("revision_number", True, TypeError),
        ("revision_number", 2, ValueError),
        ("name", "\x00", InvalidCharacterName),
        ("role", "\x00", InvalidCharacterRole),
        ("created_at", datetime(2026, 1, 1), ValueError),
        ("updated_at", BASE_TIME - timedelta(seconds=1), ValueError),
    ],
)
def test_list_item_rejects_invalid_values(
    field: str,
    value: object,
    error: type[Exception],
) -> None:
    values = {
        item_field.name: getattr(list_item(), item_field.name)
        for item_field in fields(CharacterListItem)
    }
    values[field] = value
    with pytest.raises(error):
        CharacterListItem(**values)


@pytest.mark.parametrize(("field", "value"), [("name", 1), ("role", 1)])
def test_list_item_rejects_non_string_text(field: str, value: object) -> None:
    values = {
        item_field.name: getattr(list_item(), item_field.name)
        for item_field in fields(CharacterListItem)
    }
    values[field] = value

    with pytest.raises(TypeError):
        CharacterListItem(**values)


def test_page_validates_strict_order_position_and_empty_page() -> None:
    first = list_item(2)
    second = list_item(1)
    position = CharacterListPosition(project_id(1), second.created_at, character_id(1))
    page = CharacterListPage(str(project_id(1)), (first, second), position, True)
    empty = CharacterListPage(str(project_id(1)), (), None, False)

    assert page.items == (first, second)
    assert page.next_position == position
    assert empty.items == ()
    assert not empty.has_more
    assert not hasattr(page, "total")


@pytest.mark.parametrize("case", ["items", "duplicate", "order", "position", "project", "flags"])
def test_page_rejects_invalid_container_order_or_position(case: str) -> None:
    first = list_item(2)
    second = list_item(1)
    values: dict[str, object] = {
        "project_id": str(project_id(1)),
        "items": (first, second),
        "next_position": None,
        "has_more": False,
    }
    if case == "items":
        values["items"] = [first]
    elif case == "duplicate":
        values["items"] = (first, first)
    elif case == "order":
        values["items"] = (second, first)
    elif case == "position":
        values["has_more"] = True
        values["next_position"] = CharacterListPosition(
            project_id(1),
            first.created_at,
            character_id(2),
        )
    elif case == "project":
        values["next_position"] = CharacterListPosition(
            project_id(2),
            second.created_at,
            character_id(1),
        )
    else:
        values["has_more"] = True
    with pytest.raises((TypeError, ValueError)):
        CharacterListPage(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [("has_more", 1), ("next_position", object())],
)
def test_page_rejects_wrong_flag_or_position_type(field: str, value: object) -> None:
    values: dict[str, object] = {
        "project_id": str(project_id(1)),
        "items": (),
        "next_position": None,
        "has_more": False,
    }
    values[field] = value

    with pytest.raises(TypeError):
        CharacterListPage(**values)  # type: ignore[arg-type]


def test_final_page_rejects_position_even_when_it_matches_last_item() -> None:
    item = list_item(1)
    position = CharacterListPosition(project_id(1), item.created_at, character_id(1))

    with pytest.raises(ValueError, match="final page"):
        CharacterListPage(str(project_id(1)), (item,), position, False)
