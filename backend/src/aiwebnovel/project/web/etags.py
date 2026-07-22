"""Strong ETag formatting and strict If-Match parsing for Project versions."""

import re

from aiwebnovel.domain.concurrency import MAX_CONCURRENCY_VERSION, ConcurrencyVersion

_PROJECT_ETAG_PATTERN = re.compile(r'"([1-9][0-9]*)"\Z')


class InvalidProjectIfMatch(ValueError):
    """Raised when If-Match is not one canonical strong Project ETag."""


def format_project_etag(version: ConcurrencyVersion | int) -> str:
    """Format one positive 64-bit concurrency version as a strong ETag."""
    if type(version) is ConcurrencyVersion:
        value = int(version)
    elif type(version) is int:
        value = version
    else:
        raise ValueError("version must be a positive concurrency version")
    if not 1 <= value <= MAX_CONCURRENCY_VERSION:
        raise ValueError("version must be a positive concurrency version")
    return f'"{value}"'


def parse_project_if_match(value: str) -> ConcurrencyVersion:
    """Parse exactly one quoted positive 64-bit integer ETag."""
    if type(value) is not str:
        raise InvalidProjectIfMatch
    matched = _PROJECT_ETAG_PATTERN.fullmatch(value)
    if matched is None:
        raise InvalidProjectIfMatch
    integer = int(matched.group(1))
    if integer > MAX_CONCURRENCY_VERSION:
        raise InvalidProjectIfMatch
    return ConcurrencyVersion(integer)


__all__ = ["InvalidProjectIfMatch", "format_project_etag", "parse_project_if_match"]
