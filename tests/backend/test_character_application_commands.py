"""Character application command contracts."""

from dataclasses import FrozenInstanceError, fields

import pytest

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)


def test_create_command_has_exact_primitive_fields_and_is_frozen() -> None:
    command = CreateCharacterCommand("project", "name", "role", "profile")

    assert tuple(field.name for field in fields(command)) == (
        "project_id",
        "name",
        "role",
        "profile",
    )
    assert all(type(value) is str for value in fields_as_values(command))
    assert not hasattr(command, "__dict__")
    with pytest.raises(FrozenInstanceError):
        command.name = "changed"  # type: ignore[misc]


def test_revise_command_has_exact_primitive_fields_and_is_frozen() -> None:
    command = ReviseCharacterCommand("character", 1, "name", "role", "profile")

    assert tuple(field.name for field in fields(command)) == (
        "character_id",
        "expected_version",
        "name",
        "role",
        "profile",
    )
    assert tuple(type(value) for value in fields_as_values(command)) == (
        str,
        int,
        str,
        str,
        str,
    )
    assert not hasattr(command, "__dict__")
    with pytest.raises(FrozenInstanceError):
        command.expected_version = 2  # type: ignore[misc]


def fields_as_values(command: object) -> tuple[object, ...]:
    return tuple(getattr(command, field.name) for field in fields(command))
