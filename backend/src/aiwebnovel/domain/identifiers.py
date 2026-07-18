"""Immutable ULID and typed prefixed-ULID domain primitives."""

from __future__ import annotations

import datetime as dt
import re
import secrets
import threading
import time
from collections.abc import Callable
from functools import total_ordering
from typing import Self

from aiwebnovel.domain.errors import InvalidDomainIdentifier

CROCKFORD_BASE32_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_TEXT_LENGTH = 26
ULID_TIMESTAMP_BITS = 48
ULID_RANDOMNESS_BITS = 80
MAX_ULID = (1 << 128) - 1
MAX_ULID_TIMESTAMP = (1 << ULID_TIMESTAMP_BITS) - 1
MAX_ULID_RANDOMNESS = (1 << ULID_RANDOMNESS_BITS) - 1

_CROCKFORD_DECODE = {character: index for index, character in enumerate(CROCKFORD_BASE32_ALPHABET)}
_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
_PREFIX_PATTERN = re.compile(r"[a-z][a-z0-9]{1,11}\Z", flags=re.ASCII)
_TYPE_NAME_PATTERN = re.compile(r"[A-Z][A-Za-z0-9]{0,63}\Z", flags=re.ASCII)
_RESERVED_PREFIXES = frozenset({"admin", "api", "root", "sys", "system"})


def _invalid_identifier() -> InvalidDomainIdentifier:
    """Build a fixed-message exception without retaining rejected input."""
    return InvalidDomainIdentifier()


def _require_bounded_integer(value: object, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise _invalid_identifier()
    return value


def _encode_ulid(value: int) -> str:
    remaining = value
    encoded = ["0"] * ULID_TEXT_LENGTH
    for index in range(ULID_TEXT_LENGTH - 1, -1, -1):
        encoded[index] = CROCKFORD_BASE32_ALPHABET[remaining & 31]
        remaining >>= 5
    return "".join(encoded)


def _decode_ulid(text: object) -> int:
    if not isinstance(text, str) or len(text) != ULID_TEXT_LENGTH:
        raise _invalid_identifier()

    value = 0
    for character in text.upper():
        digit = _CROCKFORD_DECODE.get(character)
        if digit is None:
            raise _invalid_identifier()
        value = (value << 5) | digit
    if value > MAX_ULID:
        raise _invalid_identifier()
    return value


def _datetime_to_unix_milliseconds(value: object) -> int:
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise _invalid_identifier()
    normalized = value.astimezone(dt.UTC)
    delta = normalized - _EPOCH
    milliseconds = delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000
    return _require_bounded_integer(milliseconds, MAX_ULID_TIMESTAMP)


@total_ordering
class Ulid:
    """A complete immutable 128-bit ULID value."""

    __slots__ = ("_value",)
    _value: int

    def __init__(self, value: int) -> None:
        object.__setattr__(self, "_value", _require_bounded_integer(value, MAX_ULID))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Ulid is immutable")

    @classmethod
    def parse(cls, text: str) -> Self:
        """Parse strict Crockford Base32 and normalize output to uppercase."""
        return cls(_decode_ulid(text))

    @classmethod
    def from_int(cls, value: int) -> Self:
        """Construct from the complete unsigned 128-bit integer value."""
        return cls(_require_bounded_integer(value, MAX_ULID))

    @classmethod
    def from_parts(cls, timestamp_ms: int, randomness: int) -> Self:
        """Construct from a 48-bit timestamp and an 80-bit random component."""
        safe_timestamp = _require_bounded_integer(timestamp_ms, MAX_ULID_TIMESTAMP)
        safe_randomness = _require_bounded_integer(randomness, MAX_ULID_RANDOMNESS)
        return cls((safe_timestamp << ULID_RANDOMNESS_BITS) | safe_randomness)

    @classmethod
    def from_datetime(cls, value: dt.datetime, *, randomness: int = 0) -> Self:
        """Construct using a timezone-aware instant, truncating below milliseconds."""
        return cls.from_parts(_datetime_to_unix_milliseconds(value), randomness)

    @classmethod
    def new(cls, generator: MonotonicUlidGenerator | None = None) -> Self:
        """Generate a new value with either the supplied or process generator."""
        generated = new_ulid() if generator is None else generator.new()
        return cls.from_int(int(generated))

    @property
    def timestamp_ms(self) -> int:
        """Return the 48-bit Unix timestamp in milliseconds."""
        return self._value >> ULID_RANDOMNESS_BITS

    @property
    def randomness(self) -> int:
        """Return the unsigned 80-bit random component."""
        return self._value & MAX_ULID_RANDOMNESS

    @property
    def datetime(self) -> dt.datetime:
        """Return the timestamp as an aware UTC datetime when representable."""
        return self.to_datetime()

    def to_datetime(self) -> dt.datetime:
        """Return the timestamp as an aware UTC datetime at millisecond precision."""
        try:
            return _EPOCH + dt.timedelta(milliseconds=self.timestamp_ms)
        except OverflowError as error:
            raise OverflowError("ULID timestamp is outside the datetime range.") from error

    def __int__(self) -> int:
        return self._value

    def __eq__(self, other: object) -> bool:
        return type(other) is Ulid and self._value == other._value

    def __lt__(self, other: object) -> bool:
        if type(other) is not Ulid:
            return NotImplemented
        return self._value < other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return _encode_ulid(self._value)

    def __repr__(self) -> str:
        return f"Ulid('{self}')"


def _utc_unix_milliseconds() -> int:
    return time.time_ns() // 1_000_000


class MonotonicUlidGenerator:
    """Generate thread-safe, strictly increasing ULIDs within one process."""

    __slots__ = ("_clock", "_last_randomness", "_last_timestamp_ms", "_lock", "_random_source")

    def __init__(
        self,
        *,
        clock: Callable[[], int] | None = None,
        random_source: Callable[[int], int] | None = None,
    ) -> None:
        self._clock = _utc_unix_milliseconds if clock is None else clock
        self._random_source = secrets.randbits if random_source is None else random_source
        self._lock = threading.Lock()
        self._last_timestamp_ms = -1
        self._last_randomness = 0

    def new(self) -> Ulid:
        """Return the next ULID without allowing clock rollback or random wraparound."""
        with self._lock:
            timestamp_ms = _require_bounded_integer(self._clock(), MAX_ULID_TIMESTAMP)
            if timestamp_ms > self._last_timestamp_ms:
                randomness = _require_bounded_integer(
                    self._random_source(ULID_RANDOMNESS_BITS),
                    MAX_ULID_RANDOMNESS,
                )
                effective_timestamp = timestamp_ms
            else:
                if self._last_randomness == MAX_ULID_RANDOMNESS:
                    raise OverflowError("ULID random space exhausted for the current millisecond.")
                effective_timestamp = self._last_timestamp_ms
                randomness = self._last_randomness + 1

            self._last_timestamp_ms = effective_timestamp
            self._last_randomness = randomness
            return Ulid.from_parts(effective_timestamp, randomness)

    __call__ = new


_PROCESS_ULID_GENERATOR = MonotonicUlidGenerator()


def new_ulid() -> Ulid:
    """Generate a ULID using the single process-wide monotonic generator."""
    return _PROCESS_ULID_GENERATOR.new()


def _validate_prefix(prefix: object) -> str:
    if (
        not isinstance(prefix, str)
        or _PREFIX_PATTERN.fullmatch(prefix) is None
        or prefix in _RESERVED_PREFIXES
    ):
        raise _invalid_identifier()
    return prefix


class PrefixedUlid:
    """An immutable validated prefix paired with a ULID value."""

    __slots__ = ("prefix", "ulid")

    prefix: str
    ulid: Ulid

    def __init__(self, prefix: str, ulid: Ulid) -> None:
        safe_prefix = _validate_prefix(prefix)
        if type(ulid) is not Ulid:
            raise _invalid_identifier()
        object.__setattr__(self, "prefix", safe_prefix)
        object.__setattr__(self, "ulid", ulid)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("PrefixedUlid is immutable")

    @classmethod
    def parse(cls, text: str) -> Self:
        """Parse a complete ``prefix_ULID`` value."""
        if not isinstance(text, str) or text.count("_") != 1:
            raise _invalid_identifier()
        prefix, encoded_ulid = text.split("_", maxsplit=1)
        return cls(_validate_prefix(prefix), Ulid.parse(encoded_ulid))

    @classmethod
    def from_ulid(cls, ulid: Ulid) -> Self:
        """Build a declared concrete identifier from an existing ULID."""
        raise _invalid_identifier()

    @classmethod
    def new(cls, generator: MonotonicUlidGenerator | None = None) -> Self:
        """Generate a value for a declared concrete identifier type."""
        generated = new_ulid() if generator is None else generator.new()
        return cls.from_ulid(generated)

    def _value_key(self) -> tuple[str, Ulid]:
        return self.prefix, self.ulid

    def __eq__(self, other: object) -> bool:
        return type(self) is type(other) and self._value_key() == other._value_key()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PrefixedUlid):
            return NotImplemented
        return self._value_key() < other._value_key()

    def __hash__(self) -> int:
        return hash((type(self), self.prefix, self.ulid))

    def __str__(self) -> str:
        return f"{self.prefix}_{self.ulid}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self}')"


def create_prefixed_ulid_type(type_name: str, prefix: str) -> type[PrefixedUlid]:
    """Declare an immutable concrete identifier type with one fixed prefix."""
    if not isinstance(type_name, str) or _TYPE_NAME_PATTERN.fullmatch(type_name) is None:
        raise _invalid_identifier()
    fixed_prefix = _validate_prefix(prefix)

    class ConcretePrefixedUlid(PrefixedUlid):
        __slots__ = ()

        def __init__(self, ulid: Ulid) -> None:
            super().__init__(fixed_prefix, ulid)

        @classmethod
        def parse(cls, text: str) -> Self:
            parsed = PrefixedUlid.parse(text)
            if parsed.prefix != fixed_prefix:
                raise _invalid_identifier()
            return cls(parsed.ulid)

        @classmethod
        def from_ulid(cls, ulid: Ulid) -> Self:
            if type(ulid) is not Ulid:
                raise _invalid_identifier()
            return cls(ulid)

    ConcretePrefixedUlid.__name__ = type_name
    ConcretePrefixedUlid.__qualname__ = type_name
    return ConcretePrefixedUlid
