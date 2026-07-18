"""UTC domain time helper tests."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from aiwebnovel.domain.time import (
    MAX_TIMESTAMP_MILLISECONDS,
    datetime_to_milliseconds,
    ensure_utc,
    milliseconds_to_datetime,
    utc_now,
)

pytestmark = pytest.mark.unit


def test_utc_now_uses_injected_clock_and_normalizes_to_utc() -> None:
    source = datetime(2025, 1, 2, 11, 4, 5, 678901, tzinfo=timezone(timedelta(hours=8)))

    result = utc_now(lambda: source)

    assert result == datetime(2025, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
    assert result.tzinfo is UTC
    assert source.utcoffset() == timedelta(hours=8)


def test_utc_now_default_is_timezone_aware_utc() -> None:
    result = utc_now()

    assert result.tzinfo is UTC
    assert result.utcoffset() == timedelta(0)


def test_ensure_utc_accepts_utc_and_rejects_naive_or_non_datetime_values() -> None:
    aware = datetime(2024, 2, 3, 4, 5, 6, tzinfo=UTC)

    assert ensure_utc(aware) == aware
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_utc(datetime(2024, 2, 3, 4, 5, 6))
    with pytest.raises(TypeError, match="datetime"):
        ensure_utc("2024-02-03")


def test_datetime_millisecond_conversion_normalizes_and_truncates() -> None:
    source = datetime(1970, 1, 1, 8, 0, 1, 234999, tzinfo=timezone(timedelta(hours=8)))

    milliseconds = datetime_to_milliseconds(source)

    assert milliseconds == 1_234
    assert milliseconds_to_datetime(milliseconds) == datetime(
        1970,
        1,
        1,
        0,
        0,
        1,
        234000,
        tzinfo=UTC,
    )


def test_millisecond_epoch_and_datetime_upper_boundary_round_trip() -> None:
    latest = datetime.max.replace(tzinfo=UTC)
    latest_milliseconds = datetime_to_milliseconds(latest)

    assert milliseconds_to_datetime(0) == datetime(1970, 1, 1, tzinfo=UTC)
    assert milliseconds_to_datetime(latest_milliseconds) == latest.replace(microsecond=999000)
    assert latest_milliseconds < MAX_TIMESTAMP_MILLISECONDS


@pytest.mark.parametrize("value", (True, 1.0, "1"))
def test_milliseconds_to_datetime_rejects_non_integer_values(value: object) -> None:
    with pytest.raises(TypeError, match="integer"):
        milliseconds_to_datetime(value)


@pytest.mark.parametrize("value", (-1, MAX_TIMESTAMP_MILLISECONDS + 1))
def test_millisecond_conversions_reject_values_outside_48_bits(value: int) -> None:
    with pytest.raises(ValueError, match="48 bits"):
        milliseconds_to_datetime(value)


def test_datetime_conversion_rejects_pre_epoch_and_unrepresentable_48_bit_value() -> None:
    with pytest.raises(ValueError, match="48 bits"):
        datetime_to_milliseconds(datetime(1969, 12, 31, 23, 59, 59, 999999, tzinfo=UTC))
    with pytest.raises(ValueError, match="represented"):
        milliseconds_to_datetime(MAX_TIMESTAMP_MILLISECONDS)


def test_datetime_conversion_rejects_naive_values() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        datetime_to_milliseconds(datetime(1970, 1, 1))
