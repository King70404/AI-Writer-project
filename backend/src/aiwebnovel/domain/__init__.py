"""Public framework-independent domain foundation contracts."""

from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.domain.errors import (
    ConcurrencyConflict,
    DomainError,
    InvalidConcurrencyVersion,
    InvalidDomainIdentifier,
    InvalidRevisionNumber,
)
from aiwebnovel.domain.identifiers import (
    MonotonicUlidGenerator,
    PrefixedUlid,
    Ulid,
    create_prefixed_ulid_type,
    new_ulid,
)
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import (
    Clock,
    datetime_to_milliseconds,
    ensure_utc,
    milliseconds_to_datetime,
    utc_now,
)

__all__ = [
    "Clock",
    "ConcurrencyConflict",
    "ConcurrencyVersion",
    "DomainError",
    "InvalidConcurrencyVersion",
    "InvalidDomainIdentifier",
    "InvalidRevisionNumber",
    "MonotonicUlidGenerator",
    "PrefixedUlid",
    "RevisionNumber",
    "Ulid",
    "assert_expected_version",
    "create_prefixed_ulid_type",
    "datetime_to_milliseconds",
    "ensure_utc",
    "milliseconds_to_datetime",
    "new_ulid",
    "utc_now",
]
