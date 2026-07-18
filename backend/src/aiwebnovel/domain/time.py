"""UTC-only time helpers shared by domain primitives."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

TIMESTAMP_BITS = 48
MIN_TIMESTAMP_MILLISECONDS = 0
MAX_TIMESTAMP_MILLISECONDS = (1 << TIMESTAMP_BITS) - 1

_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class Clock(Protocol):
    """Callable source of timezone-aware datetimes."""

    def __call__(self) -> datetime:
        """Return the clock's current datetime."""
        ...


def utc_now(clock: Clock | Callable[[], datetime] | None = None) -> datetime:
    """Return the current time normalized to an aware UTC datetime."""
    value = datetime.now(UTC) if clock is None else clock()
    return ensure_utc(value)


def ensure_utc(value: datetime) -> datetime:
    """Normalize one aware datetime to UTC, rejecting naive values."""
    if not isinstance(value, datetime):
        raise TypeError("value must be a datetime")
    if value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def datetime_to_milliseconds(value: datetime) -> int:
    """Return Unix milliseconds, truncating sub-millisecond precision."""
    normalized = ensure_utc(value)
    delta = normalized - _UNIX_EPOCH
    total_microseconds = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    return _validate_timestamp_milliseconds(total_microseconds // 1_000)


def milliseconds_to_datetime(value: int) -> datetime:
    """Convert a 48-bit Unix millisecond value to an aware UTC datetime."""
    milliseconds = _validate_timestamp_milliseconds(value)
    try:
        return _UNIX_EPOCH + timedelta(milliseconds=milliseconds)
    except OverflowError as exc:
        raise ValueError("timestamp cannot be represented as a datetime") from exc


def _validate_timestamp_milliseconds(value: object) -> int:
    if type(value) is not int:
        raise TypeError("timestamp milliseconds must be an integer")
    if not MIN_TIMESTAMP_MILLISECONDS <= value <= MAX_TIMESTAMP_MILLISECONDS:
        raise ValueError("timestamp milliseconds must fit in 48 bits")
    return value
