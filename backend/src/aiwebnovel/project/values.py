"""Immutable text value objects owned by the Project domain."""

from dataclasses import dataclass

from aiwebnovel.project.errors import InvalidProjectDescription, InvalidProjectTitle

MAX_PROJECT_TITLE_LENGTH = 120
MAX_PROJECT_DESCRIPTION_LENGTH = 2_000
_UNICODE_LINE_SEPARATORS = frozenset({"\u2028", "\u2029"})


def _is_c0_or_c1_control(character: str) -> bool:
    code_point = ord(character)
    return code_point <= 0x1F or 0x7F <= code_point <= 0x9F


@dataclass(frozen=True, slots=True)
class ProjectTitle:
    """A normalized non-empty Project title without control characters."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or any(
            _is_c0_or_c1_control(char) or char in _UNICODE_LINE_SEPARATORS for char in self.value
        ):
            raise InvalidProjectTitle
        normalized = self.value.strip()
        if not 1 <= len(normalized) <= MAX_PROJECT_TITLE_LENGTH:
            raise InvalidProjectTitle
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProjectDescription:
    """A bounded Project description with canonical LF line endings."""

    value: str = ""

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise InvalidProjectDescription
        normalized = self.value.replace("\r\n", "\n").replace("\r", "\n")
        if len(normalized) > MAX_PROJECT_DESCRIPTION_LENGTH or any(
            _is_c0_or_c1_control(char) and char not in {"\n", "\t"} for char in normalized
        ):
            raise InvalidProjectDescription
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
