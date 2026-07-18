"""Immutable human-readable revision numbers."""

from functools import total_ordering

from aiwebnovel.domain.errors import InvalidRevisionNumber

MAX_REVISION_NUMBER = (1 << 63) - 1


@total_ordering
class RevisionNumber:
    """A positive revision within one stable object's history."""

    __slots__ = ("value",)

    value: int

    def __init__(self, value: int = 1) -> None:
        if type(value) is not int or not 1 <= value <= MAX_REVISION_NUMBER:
            raise InvalidRevisionNumber
        object.__setattr__(self, "value", value)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("RevisionNumber is immutable")

    def __int__(self) -> int:
        """Return the primitive integer representation."""
        return self.value

    def __eq__(self, other: object) -> bool:
        return type(other) is RevisionNumber and self.value == other.value

    def __lt__(self, other: object) -> bool:
        if type(other) is not RevisionNumber:
            return NotImplemented
        return self.value < other.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __repr__(self) -> str:
        return f"RevisionNumber(value={self.value})"

    def next(self) -> "RevisionNumber":
        """Return the next revision without changing this instance."""
        if self.value == MAX_REVISION_NUMBER:
            raise InvalidRevisionNumber
        return RevisionNumber(self.value + 1)
