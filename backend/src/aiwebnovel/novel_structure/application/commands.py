"""Immutable primitive inputs for novel-structure write use cases."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateOutlineCommand:
    project_id: str
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class UpdateOutlineCommand:
    outline_id: str
    expected_version: int
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class CreateVolumeCommand:
    project_id: str
    title: str
    summary: str
    position: int


@dataclass(frozen=True, slots=True)
class UpdateVolumeCommand:
    volume_id: str
    expected_version: int
    title: str
    summary: str
    position: int


@dataclass(frozen=True, slots=True)
class CreateChapterCommand:
    project_id: str
    volume_id: str
    title: str
    summary: str
    position: int


@dataclass(frozen=True, slots=True)
class UpdateChapterCommand:
    chapter_id: str
    expected_version: int
    title: str
    summary: str
    position: int


__all__ = [
    "CreateChapterCommand",
    "CreateOutlineCommand",
    "CreateVolumeCommand",
    "UpdateChapterCommand",
    "UpdateOutlineCommand",
    "UpdateVolumeCommand",
]
