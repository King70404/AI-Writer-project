"""Immutable text value objects owned by the Story Bible domain."""

from dataclasses import dataclass

from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleContent,
    InvalidStoryBibleTitle,
)

MAX_STORY_BIBLE_TITLE_LENGTH = 120
MAX_STORY_BIBLE_CONTENT_LENGTH = 50_000
_UNICODE_LINE_SEPARATORS = frozenset({"\u2028", "\u2029"})


def _is_c0_or_c1_control(character: str) -> bool:
    code_point = ord(character)
    return code_point <= 0x1F or 0x7F <= code_point <= 0x9F


@dataclass(frozen=True, slots=True)
class StoryBibleTitle:
    """A stripped, non-empty title without control or separator characters."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or any(
            _is_c0_or_c1_control(character) or character in _UNICODE_LINE_SEPARATORS
            for character in self.value
        ):
            raise InvalidStoryBibleTitle
        normalized = self.value.strip()
        if not 1 <= len(normalized) <= MAX_STORY_BIBLE_TITLE_LENGTH:
            raise InvalidStoryBibleTitle
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class StoryBibleContent:
    """A bounded plain-text snapshot with canonical LF line endings."""

    value: str = ""

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise InvalidStoryBibleContent
        normalized = self.value.replace("\r\n", "\n").replace("\r", "\n")
        if len(normalized) > MAX_STORY_BIBLE_CONTENT_LENGTH or any(
            (_is_c0_or_c1_control(character) and character not in {"\n", "\t"})
            or character in _UNICODE_LINE_SEPARATORS
            for character in normalized
        ):
            raise InvalidStoryBibleContent
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
