"""Immutable values shared by Outline, Volume, and Chapter revisions."""

from dataclasses import dataclass

from aiwebnovel.novel_structure.errors import (
    InvalidNovelStructurePosition,
    InvalidNovelStructureSummary,
    InvalidNovelStructureTitle,
)

MAX_NOVEL_STRUCTURE_TITLE_LENGTH = 120
MAX_NOVEL_STRUCTURE_SUMMARY_LENGTH = 2_000
MAX_NOVEL_STRUCTURE_POSITION = (1 << 63) - 1
_UNICODE_LINE_SEPARATORS = frozenset({"\u2028", "\u2029"})


def _is_c0_or_c1_control(character: str) -> bool:
    code_point = ord(character)
    return code_point <= 0x1F or 0x7F <= code_point <= 0x9F


@dataclass(frozen=True, slots=True)
class NovelStructureTitle:
    """A stripped, non-empty title without control characters."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or any(
            _is_c0_or_c1_control(character) or character in _UNICODE_LINE_SEPARATORS
            for character in self.value
        ):
            raise InvalidNovelStructureTitle
        normalized = self.value.strip()
        if not 1 <= len(normalized) <= MAX_NOVEL_STRUCTURE_TITLE_LENGTH:
            raise InvalidNovelStructureTitle
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class NovelStructureSummary:
    """A bounded optional summary with canonical LF line endings."""

    value: str = ""

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise InvalidNovelStructureSummary
        normalized = self.value.replace("\r\n", "\n").replace("\r", "\n")
        if len(normalized) > MAX_NOVEL_STRUCTURE_SUMMARY_LENGTH or any(
            (_is_c0_or_c1_control(character) and character not in {"\n", "\t"})
            or character in _UNICODE_LINE_SEPARATORS
            for character in normalized
        ):
            raise InvalidNovelStructureSummary
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class NovelStructurePosition:
    """A positive signed-64-bit position within a parent collection."""

    value: int

    def __post_init__(self) -> None:
        if (
            type(self.value) is not int
            or self.value < 1
            or self.value > MAX_NOVEL_STRUCTURE_POSITION
        ):
            raise InvalidNovelStructurePosition

    def __int__(self) -> int:
        return self.value
