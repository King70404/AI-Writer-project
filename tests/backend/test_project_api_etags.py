"""Canonical Project ETag and If-Match protocol tests."""

import pytest

from aiwebnovel.domain.concurrency import MAX_CONCURRENCY_VERSION, ConcurrencyVersion
from aiwebnovel.project.web.etags import (
    InvalidProjectIfMatch,
    format_project_etag,
    parse_project_if_match,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("version", [1, 2, MAX_CONCURRENCY_VERSION])
def test_format_project_etag_is_one_strong_quoted_integer(version: int) -> None:
    assert format_project_etag(version) == f'"{version}"'
    assert format_project_etag(ConcurrencyVersion(version)) == f'"{version}"'


@pytest.mark.parametrize("value", [True, False, 0, -1, MAX_CONCURRENCY_VERSION + 1, "1"])
def test_format_project_etag_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        format_project_etag(value)  # type: ignore[arg-type]


def test_parse_project_if_match_returns_domain_version() -> None:
    assert parse_project_if_match('"1"') == ConcurrencyVersion(1)
    assert parse_project_if_match(f'"{MAX_CONCURRENCY_VERSION}"') == ConcurrencyVersion(
        MAX_CONCURRENCY_VERSION
    )


@pytest.mark.parametrize(
    "value",
    ["", "1", 'W/"1"', "*", '"1", "2"', '"0"', '"-1"', '"true"', '"01"', ' "1"'],
)
def test_parse_project_if_match_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(InvalidProjectIfMatch):
        parse_project_if_match(value)


def test_parse_project_if_match_rejects_overflow_without_domain_leak() -> None:
    with pytest.raises(InvalidProjectIfMatch):
        parse_project_if_match(f'"{MAX_CONCURRENCY_VERSION + 1}"')


def test_parse_project_if_match_rejects_non_string_without_coercion() -> None:
    with pytest.raises(InvalidProjectIfMatch):
        parse_project_if_match(1)  # type: ignore[arg-type]
