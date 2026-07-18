"""Immutable revision-number tests."""

import pytest
from fastapi.encoders import jsonable_encoder

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import InvalidRevisionNumber
from aiwebnovel.domain.revisions import MAX_REVISION_NUMBER, RevisionNumber

pytestmark = pytest.mark.unit


def test_revision_defaults_to_first_revision_and_supports_integer_conversion() -> None:
    revision = RevisionNumber()

    assert revision.value == 1
    assert int(revision) == 1
    assert repr(revision) == "RevisionNumber(value=1)"


def test_revision_comparison_hashing_and_next_are_value_based_and_immutable() -> None:
    first = RevisionNumber(1)
    second = first.next()

    assert first == RevisionNumber(1)
    assert first < second
    assert len({first, RevisionNumber(1), second}) == 2
    assert first.value == 1
    assert second.value == 2
    assert second is not first
    with pytest.raises(AttributeError, match="immutable"):
        first.value = 2


def test_revision_requires_explicit_integer_serialization() -> None:
    revision = RevisionNumber(2)

    with pytest.raises(ValueError):
        jsonable_encoder(revision)

    assert int(revision) == 2


@pytest.mark.parametrize(
    "value",
    (0, -1, True, 1.0, "1", ConcurrencyVersion(1)),
)
def test_revision_rejects_invalid_or_cross_domain_values(value: object) -> None:
    with pytest.raises(InvalidRevisionNumber):
        RevisionNumber(value)


def test_revision_accepts_signed_64_bit_maximum_and_next_rejects_overflow() -> None:
    maximum = RevisionNumber(MAX_REVISION_NUMBER)

    assert int(maximum) == (1 << 63) - 1
    with pytest.raises(InvalidRevisionNumber):
        maximum.next()
    with pytest.raises(InvalidRevisionNumber):
        RevisionNumber(MAX_REVISION_NUMBER + 1)


def test_revision_limit_cannot_be_bypassed_with_a_class_attribute() -> None:
    type.__setattr__(RevisionNumber, "maximum", MAX_REVISION_NUMBER + 1)
    try:
        with pytest.raises(InvalidRevisionNumber):
            RevisionNumber(MAX_REVISION_NUMBER + 1)
    finally:
        type.__delattr__(RevisionNumber, "maximum")


def test_revision_and_concurrency_version_are_not_interchangeable() -> None:
    revision = RevisionNumber(1)
    concurrency = ConcurrencyVersion(1)

    assert revision != concurrency
    with pytest.raises(TypeError):
        _ = revision < concurrency
