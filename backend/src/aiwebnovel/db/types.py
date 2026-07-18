"""SQLAlchemy adapters for framework-independent domain value objects."""

from datetime import UTC, datetime

from sqlalchemy.engine import Dialect
from sqlalchemy.types import DateTime as SqlDateTime
from sqlalchemy.types import Integer, Text, TypeDecorator

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import (
    InvalidConcurrencyVersion,
    InvalidDomainIdentifier,
    InvalidRevisionNumber,
)
from aiwebnovel.domain.identifiers import PrefixedUlid, Ulid
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import ensure_utc

ULID_TEXT_LENGTH = 26
MAX_PREFIXED_ULID_TEXT_LENGTH = 39


class UlidType(TypeDecorator[Ulid]):
    """Persist :class:`Ulid` as canonical 26-character text."""

    impl = Text
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(length=ULID_TEXT_LENGTH)

    @property
    def python_type(self) -> type[Ulid]:
        """Expose the domain value type represented by this adapter."""
        return Ulid

    def process_bind_param(self, value: Ulid | None, dialect: Dialect) -> str | None:
        """Validate the domain boundary and emit canonical storage text."""
        if value is None:
            return None
        if type(value) is not Ulid:
            raise TypeError("UlidType only accepts Ulid values")
        return str(value)

    def process_result_value(self, value: object | None, dialect: Dialect) -> Ulid | None:
        """Restore a domain value and reject malformed stored data."""
        if value is None:
            return None
        if type(value) is not str:
            raise InvalidDomainIdentifier
        return Ulid.parse(value)


class PrefixedUlidType(TypeDecorator[PrefixedUlid]):
    """Persist a base or concrete prefixed ULID as bounded canonical text."""

    impl = Text
    cache_ok = True

    def __init__(self, value_type: type[PrefixedUlid] = PrefixedUlid) -> None:
        if not isinstance(value_type, type) or not issubclass(value_type, PrefixedUlid):
            raise TypeError("value_type must be a PrefixedUlid type")
        self.value_type = value_type
        super().__init__(length=MAX_PREFIXED_ULID_TEXT_LENGTH)

    @property
    def python_type(self) -> type[PrefixedUlid]:
        """Expose the configured concrete domain identifier type."""
        return self.value_type

    def process_bind_param(self, value: PrefixedUlid | None, dialect: Dialect) -> str | None:
        """Reject primitives and identifiers from a different concrete type."""
        if value is None:
            return None
        accepts_value = (
            isinstance(value, PrefixedUlid)
            if self.value_type is PrefixedUlid
            else type(value) is self.value_type
        )
        if not accepts_value:
            raise TypeError("PrefixedUlidType received an incompatible domain identifier")
        return str(value)

    def process_result_value(
        self,
        value: object | None,
        dialect: Dialect,
    ) -> PrefixedUlid | None:
        """Restore the configured identifier type and reject database pollution."""
        if value is None:
            return None
        if type(value) is not str:
            raise InvalidDomainIdentifier
        return self.value_type.parse(value)


class RevisionNumberType(TypeDecorator[RevisionNumber]):
    """Persist :class:`RevisionNumber` as a validated SQLite integer."""

    impl = Integer
    cache_ok = True

    @property
    def python_type(self) -> type[RevisionNumber]:
        """Expose the domain value type represented by this adapter."""
        return RevisionNumber

    def process_bind_param(
        self,
        value: RevisionNumber | None,
        dialect: Dialect,
    ) -> int | None:
        """Accept only revision domain values at the persistence boundary."""
        if value is None:
            return None
        if type(value) is not RevisionNumber:
            raise TypeError("RevisionNumberType only accepts RevisionNumber values")
        return int(value)

    def process_result_value(
        self,
        value: object | None,
        dialect: Dialect,
    ) -> RevisionNumber | None:
        """Restore a revision and reject non-integer or out-of-range storage."""
        if value is None:
            return None
        if type(value) is not int:
            raise InvalidRevisionNumber
        return RevisionNumber(value)


class ConcurrencyVersionType(TypeDecorator[ConcurrencyVersion]):
    """Persist :class:`ConcurrencyVersion` as a validated SQLite integer."""

    impl = Integer
    cache_ok = True

    @property
    def python_type(self) -> type[ConcurrencyVersion]:
        """Expose the domain value type represented by this adapter."""
        return ConcurrencyVersion

    def process_bind_param(
        self,
        value: ConcurrencyVersion | None,
        dialect: Dialect,
    ) -> int | None:
        """Accept only concurrency domain values at the persistence boundary."""
        if value is None:
            return None
        if type(value) is not ConcurrencyVersion:
            raise TypeError("ConcurrencyVersionType only accepts ConcurrencyVersion values")
        return int(value)

    def process_result_value(
        self,
        value: object | None,
        dialect: Dialect,
    ) -> ConcurrencyVersion | None:
        """Restore a concurrency version and reject polluted storage."""
        if value is None:
            return None
        if type(value) is not int:
            raise InvalidConcurrencyVersion
        return ConcurrencyVersion(value)


class UtcDateTimeType(TypeDecorator[datetime]):
    """Persist aware instants as naive UTC and restore aware UTC values."""

    impl = SqlDateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=False)

    @property
    def python_type(self) -> type[datetime]:
        """Expose the aware datetime domain boundary represented by this adapter."""
        return datetime

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> datetime | None:
        """Reject naive values and store the same instant in canonical UTC."""
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("UtcDateTimeType only accepts datetime values")
        return ensure_utc(value).replace(tzinfo=None)

    def process_result_value(
        self,
        value: object | None,
        dialect: Dialect,
    ) -> datetime | None:
        """Interpret SQLite's timezone-free value as canonical UTC."""
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise ValueError("Stored UTC datetime is invalid")
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        if value.utcoffset() is None:
            raise ValueError("Stored UTC datetime is invalid")
        return value.astimezone(UTC)
