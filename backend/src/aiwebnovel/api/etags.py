"""Canonical strong ETag formatting and strict If-Match parsing."""

import re

from aiwebnovel.domain.concurrency import MAX_CONCURRENCY_VERSION, ConcurrencyVersion

_STRONG_ETAG_PATTERN = re.compile(r'"([1-9][0-9]*)"\Z')


class InvalidIfMatch(ValueError):
    """Raised when If-Match is not one canonical strong version ETag."""


def format_strong_etag(version: ConcurrencyVersion | int) -> str:
    """Format one positive signed-64-bit version as a strong ETag."""
    if type(version) is ConcurrencyVersion:
        value = int(version)
    elif type(version) is int:
        value = version
    else:
        raise ValueError("version must be a positive concurrency version")
    if not 1 <= value <= MAX_CONCURRENCY_VERSION:
        raise ValueError("version must be a positive concurrency version")
    return f'"{value}"'


def parse_strong_if_match(value: str) -> ConcurrencyVersion:
    """Parse exactly one quoted positive signed-64-bit integer ETag."""
    if type(value) is not str:
        raise InvalidIfMatch
    matched = _STRONG_ETAG_PATTERN.fullmatch(value)
    if matched is None:
        raise InvalidIfMatch
    integer = int(matched.group(1))
    if integer > MAX_CONCURRENCY_VERSION:
        raise InvalidIfMatch
    return ConcurrencyVersion(integer)


__all__ = ["InvalidIfMatch", "format_strong_etag", "parse_strong_if_match"]
