"""Raw and immutable Project application command contracts."""

from dataclasses import FrozenInstanceError, fields

import pytest

from aiwebnovel.project.application.commands import (
    CreateProjectCommand,
    ReviseProjectCommand,
)

pytestmark = pytest.mark.unit


def test_create_project_command_has_only_raw_boundary_fields() -> None:
    command = CreateProjectCommand(title="  Raw title  ")

    assert command.title == "  Raw title  "
    assert command.description == ""
    assert tuple(field.name for field in fields(command)) == ("title", "description")
    assert not hasattr(command, "__dict__")


def test_revise_project_command_has_only_full_replacement_fields() -> None:
    command = ReviseProjectCommand(
        project_id="raw-project-id",
        expected_version=7,
        title="Replacement",
    )

    assert command == ReviseProjectCommand("raw-project-id", 7, "Replacement", "")
    assert tuple(field.name for field in fields(command)) == (
        "project_id",
        "expected_version",
        "title",
        "description",
    )
    assert not hasattr(command, "revision_id")
    assert not hasattr(command, "revision_number")


@pytest.mark.parametrize(
    "command",
    [
        CreateProjectCommand("Title", "Description"),
        ReviseProjectCommand("project-id", 1, "Title", "Description"),
    ],
)
def test_project_commands_are_frozen_and_slotted(command: object) -> None:
    with pytest.raises(FrozenInstanceError):
        command.title = "changed"  # type: ignore[attr-defined]

    assert not hasattr(command, "__dict__")


def test_command_construction_does_not_validate_or_transform_raw_values() -> None:
    marker = object()

    create = CreateProjectCommand(marker, marker)  # type: ignore[arg-type]
    revise = ReviseProjectCommand(marker, marker, marker, marker)  # type: ignore[arg-type]

    assert create.title is marker
    assert create.description is marker
    assert revise.project_id is marker
    assert revise.expected_version is marker
    assert revise.title is marker
    assert revise.description is marker
