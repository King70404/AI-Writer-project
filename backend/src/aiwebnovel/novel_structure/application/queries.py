"""Immutable primitive inputs for novel-structure current-state queries."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetOutlineQuery:
    outline_id: str


@dataclass(frozen=True, slots=True)
class GetOutlineForProjectQuery:
    project_id: str


@dataclass(frozen=True, slots=True)
class GetVolumeQuery:
    volume_id: str


@dataclass(frozen=True, slots=True)
class ListVolumesQuery:
    project_id: str


@dataclass(frozen=True, slots=True)
class GetChapterQuery:
    chapter_id: str


@dataclass(frozen=True, slots=True)
class GetChapterContentQuery:
    chapter_id: str


@dataclass(frozen=True, slots=True)
class ListChaptersQuery:
    volume_id: str


__all__ = [
    "GetChapterContentQuery",
    "GetChapterQuery",
    "GetOutlineForProjectQuery",
    "GetOutlineQuery",
    "GetVolumeQuery",
    "ListChaptersQuery",
    "ListVolumesQuery",
]
