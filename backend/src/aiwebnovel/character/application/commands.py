"""Immutable primitive inputs for Character write use cases."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateCharacterCommand:
    """Request creation of one Character owned by an existing Project."""

    project_id: str
    name: str
    role: str
    profile: str


@dataclass(frozen=True, slots=True)
class ReviseCharacterCommand:
    """Replace the complete current Character card."""

    character_id: str
    expected_version: int
    name: str
    role: str
    profile: str


__all__ = ["CreateCharacterCommand", "ReviseCharacterCommand"]
