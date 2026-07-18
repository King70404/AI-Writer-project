"""Optimistic-concurrency version tests."""

import pytest
from fastapi.encoders import jsonable_encoder

from aiwebnovel.domain.concurrency import (
    MAX_CONCURRENCY_VERSION,
    ConcurrencyVersion,
    assert_expected_version,
)
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber

pytestmark = pytest.mark.unit


def test_concurrency_version_defaults_to_one_and_supports_value_operations() -> None:
    first = ConcurrencyVersion()
    second = first.next()

    assert int(first) == 1
    assert first == ConcurrencyVersion(1)
    assert first < second
    assert hash(first) == hash(ConcurrencyVersion(1))
    assert int(second) == 2
    assert first.value == 1
    with pytest.raises(AttributeError, match="immutable"):
        first.value = 2


def test_concurrency_version_requires_explicit_integer_serialization() -> None:
    version = ConcurrencyVersion(2)

    with pytest.raises(ValueError):
        jsonable_encoder(version)

    assert int(version) == 2


@pytest.mark.parametrize(
    "value",
    (0, -1, True, 1.0, "1", RevisionNumber(1)),
)
def test_concurrency_version_rejects_invalid_or_cross_domain_values(value: object) -> None:
    with pytest.raises(InvalidConcurrencyVersion):
        ConcurrencyVersion(value)


def test_concurrency_version_accepts_maximum_and_next_rejects_overflow() -> None:
    maximum = ConcurrencyVersion(MAX_CONCURRENCY_VERSION)

    assert int(maximum) == (1 << 63) - 1
    with pytest.raises(InvalidConcurrencyVersion):
        maximum.next()
    with pytest.raises(InvalidConcurrencyVersion):
        ConcurrencyVersion(MAX_CONCURRENCY_VERSION + 1)


def test_concurrency_limit_cannot_be_bypassed_with_a_class_attribute() -> None:
    type.__setattr__(ConcurrencyVersion, "maximum", MAX_CONCURRENCY_VERSION + 1)
    try:
        with pytest.raises(InvalidConcurrencyVersion):
            ConcurrencyVersion(MAX_CONCURRENCY_VERSION + 1)
    finally:
        type.__delattr__(ConcurrencyVersion, "maximum")


def test_matching_expected_version_returns_none_without_mutation() -> None:
    actual = ConcurrencyVersion(7)
    expected = ConcurrencyVersion(7)

    result = assert_expected_version(actual, expected)

    assert result is None
    assert actual == ConcurrencyVersion(7)
    assert expected == ConcurrencyVersion(7)


def test_conflict_reports_expected_then_actual_as_safe_integers() -> None:
    actual = ConcurrencyVersion(8)
    expected = ConcurrencyVersion(7)

    with pytest.raises(ConcurrencyConflict) as captured:
        assert_expected_version(actual, expected)

    assert captured.value.expected_version == 7
    assert captured.value.actual_version == 8
    assert type(captured.value.expected_version) is int
    assert type(captured.value.actual_version) is int
    assert actual == ConcurrencyVersion(8)
    assert expected == ConcurrencyVersion(7)


@pytest.mark.parametrize(
    ("actual", "expected"),
    (
        (RevisionNumber(1), ConcurrencyVersion(1)),
        (ConcurrencyVersion(1), RevisionNumber(1)),
    ),
)
def test_expected_version_assertion_rejects_cross_domain_types(
    actual: object,
    expected: object,
) -> None:
    with pytest.raises(InvalidConcurrencyVersion):
        assert_expected_version(actual, expected)
