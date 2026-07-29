"""Immutable text value objects owned by the Character domain."""

from dataclasses import dataclass

from aiwebnovel.character.errors import (
    InvalidCharacterName,
    InvalidCharacterProfile,
    InvalidCharacterRole,
)

MAX_CHARACTER_NAME_LENGTH = 120
MAX_CHARACTER_ROLE_LENGTH = 120
MAX_CHARACTER_PROFILE_LENGTH = 50_000
_UNICODE_LINE_SEPARATORS = frozenset({"\u2028", "\u2029"})


def _is_c0_or_c1_control(character: str) -> bool:
    code_point = ord(character)
    return code_point <= 0x1F or 0x7F <= code_point <= 0x9F


@dataclass(frozen=True, slots=True)
class CharacterName:
    """A stripped, non-empty Character name."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or any(
            _is_c0_or_c1_control(character) or character in _UNICODE_LINE_SEPARATORS
            for character in self.value
        ):
            raise InvalidCharacterName
        normalized = self.value.strip()
        if not 1 <= len(normalized) <= MAX_CHARACTER_NAME_LENGTH:
            raise InvalidCharacterName
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CharacterRole:
    """A stripped, bounded free-text narrative role."""

    value: str = ""

    def __post_init__(self) -> None:
        if type(self.value) is not str or any(
            _is_c0_or_c1_control(character) or character in _UNICODE_LINE_SEPARATORS
            for character in self.value
        ):
            raise InvalidCharacterRole
        normalized = self.value.strip()
        if len(normalized) > MAX_CHARACTER_ROLE_LENGTH:
            raise InvalidCharacterRole
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CharacterProfile:
    """A bounded plain-text Character card with canonical LF line endings."""

    value: str = ""

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise InvalidCharacterProfile
        normalized = self.value.replace("\r\n", "\n").replace("\r", "\n")
        if len(normalized) > MAX_CHARACTER_PROFILE_LENGTH or any(
            (_is_c0_or_c1_control(character) and character not in {"\n", "\t"})
            or character in _UNICODE_LINE_SEPARATORS
            for character in normalized
        ):
            raise InvalidCharacterProfile
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
