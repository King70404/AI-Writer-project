"""Immutable optimistic-concurrency versions and conflict assertion."""

from functools import total_ordering

from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidConcurrencyVersion

MAX_CONCURRENCY_VERSION = (1 << 63) - 1


@total_ordering
class ConcurrencyVersion:
    """A positive database-row concurrency version."""

    __slots__ = ("value",)

    value: int

    def __init__(self, value: int = 1) -> None:
        if type(value) is not int or not 1 <= value <= MAX_CONCURRENCY_VERSION:
            raise InvalidConcurrencyVersion
        object.__setattr__(self, "value", value)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ConcurrencyVersion is immutable")

    def __int__(self) -> int:
        """Return the primitive integer representation."""
        return self.value

    def __eq__(self, other: object) -> bool:
        return type(other) is ConcurrencyVersion and self.value == other.value

    def __lt__(self, other: object) -> bool:
        if type(other) is not ConcurrencyVersion:
            return NotImplemented
        return self.value < other.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __repr__(self) -> str:
        return f"ConcurrencyVersion(value={self.value})"

    def next(self) -> "ConcurrencyVersion":
        """Return the next concurrency version without changing this instance."""
        if self.value == MAX_CONCURRENCY_VERSION:
            raise InvalidConcurrencyVersion
        return ConcurrencyVersion(self.value + 1)


def assert_expected_version(
    actual: ConcurrencyVersion,
    expected: ConcurrencyVersion,
) -> None:
    """Raise a structured conflict unless expected and actual versions match."""
    if type(actual) is not ConcurrencyVersion or type(expected) is not ConcurrencyVersion:
        raise InvalidConcurrencyVersion
    if actual != expected:
        raise ConcurrencyConflict(
            expected_version=int(expected),
            actual_version=int(actual),
        )
