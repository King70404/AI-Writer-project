"""Deterministic tests for raw, monotonic, and typed prefixed ULIDs."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.encoders import jsonable_encoder

import aiwebnovel.domain.identifiers as identifiers_module
from aiwebnovel.domain.errors import (
    ConcurrencyConflict,
    InvalidConcurrencyVersion,
    InvalidDomainIdentifier,
)
from aiwebnovel.domain.identifiers import (
    MAX_ULID,
    MAX_ULID_RANDOMNESS,
    MAX_ULID_TIMESTAMP,
    MonotonicUlidGenerator,
    PrefixedUlid,
    Ulid,
    create_prefixed_ulid_type,
    new_ulid,
)

pytestmark = pytest.mark.unit

KNOWN_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
KNOWN_TIMESTAMP_MS = 1_469_922_850_259


def _constant_clock(value: int) -> Callable[[], int]:
    return lambda: value


def _constant_random(value: int) -> Callable[[int], int]:
    return lambda _bits: value


def test_known_ulid_parses_normalizes_and_exposes_timestamp() -> None:
    parsed = Ulid.parse(KNOWN_ULID.lower())

    assert str(parsed) == KNOWN_ULID
    assert parsed.timestamp_ms == KNOWN_TIMESTAMP_MS
    assert parsed.to_datetime() == datetime(2016, 7, 30, 23, 54, 10, 259_000, tzinfo=UTC)
    assert parsed.datetime.tzinfo is UTC
    assert repr(parsed) == f"Ulid('{KNOWN_ULID}')"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "0" * 25,
        "0" * 27,
        "0" * 25 + "I",
        "0" * 25 + "L",
        "0" * 25 + "O",
        "0" * 25 + "U",
        "0" * 25 + "_",
        "0" * 25 + " ",
        "0" * 25 + "\n",
        "8" + "0" * 25,
    ],
)
def test_ulid_rejects_invalid_text_without_echoing_it(text: str) -> None:
    with pytest.raises(InvalidDomainIdentifier) as captured:
        Ulid.parse(text)

    if text:
        assert text not in str(captured.value)
    assert str(captured.value) == "The domain identifier is invalid."


@pytest.mark.parametrize("value", [-1, MAX_ULID + 1, True, False, 1.5, "1"])
def test_ulid_rejects_values_outside_the_complete_128_bit_range(value: object) -> None:
    with pytest.raises(InvalidDomainIdentifier):
        Ulid.from_int(value)


def test_ulid_integer_round_trip_boundaries_and_sorting() -> None:
    values = [MAX_ULID, 1 << 80, 0, 1, (1 << 127) + 5]
    parsed = [Ulid.from_int(value) for value in values]

    assert [int(value) for value in sorted(parsed)] == sorted(values)
    assert all(Ulid.parse(str(value)) == value for value in parsed)
    assert len({Ulid.from_int(7), Ulid.parse(str(Ulid.from_int(7)))}) == 1


def test_ulid_parts_and_datetime_round_trip_truncates_submilliseconds() -> None:
    source = datetime(2025, 2, 3, 4, 5, 6, 987_654, tzinfo=timezone(timedelta(hours=8)))
    result = Ulid.from_datetime(source, randomness=123)

    assert result.randomness == 123
    assert result.to_datetime() == datetime(2025, 2, 2, 20, 5, 6, 987_000, tzinfo=UTC)
    assert Ulid.from_parts(result.timestamp_ms, result.randomness) == result


@pytest.mark.parametrize(
    ("timestamp", "randomness"),
    [
        (-1, 0),
        (MAX_ULID_TIMESTAMP + 1, 0),
        (0, -1),
        (0, MAX_ULID_RANDOMNESS + 1),
        (True, 0),
        (0, False),
    ],
)
def test_ulid_parts_reject_invalid_component_ranges(timestamp: object, randomness: object) -> None:
    with pytest.raises(InvalidDomainIdentifier):
        Ulid.from_parts(timestamp, randomness)


def test_ulid_datetime_requires_aware_utc_representable_value() -> None:
    with pytest.raises(InvalidDomainIdentifier):
        Ulid.from_datetime(datetime(2025, 1, 1))
    with pytest.raises(InvalidDomainIdentifier):
        Ulid.from_datetime(datetime(1969, 12, 31, 23, 59, 59, 999_000, tzinfo=UTC))
    with pytest.raises(OverflowError, match="outside the datetime range"):
        Ulid.from_parts(MAX_ULID_TIMESTAMP, 0).to_datetime()


def test_ulid_is_immutable() -> None:
    value = Ulid.from_int(1)

    with pytest.raises(AttributeError, match="immutable"):
        value._value = 2

    assert int(value) == 1


def test_ulid_new_supports_injected_and_process_generators() -> None:
    generator = MonotonicUlidGenerator(
        clock=_constant_clock(2_500),
        random_source=_constant_random(6),
    )

    controlled = Ulid.new(generator)
    process_value = Ulid.new()

    assert controlled == Ulid.from_parts(2_500, 6)
    assert Ulid.parse(str(process_value)) == process_value


def test_monotonic_generator_uses_new_timestamp_randomness_and_increments_same_millisecond() -> (
    None
):
    timestamps = iter([1_000, 1_000, 1_001, 1_001])
    random_values = iter([50, 2])
    generator = MonotonicUlidGenerator(
        clock=lambda: next(timestamps),
        random_source=lambda _bits: next(random_values),
    )

    values = [generator.new() for _ in range(4)]

    assert [value.timestamp_ms for value in values] == [1_000, 1_000, 1_001, 1_001]
    assert [value.randomness for value in values] == [50, 51, 2, 3]
    assert all(left < right for left, right in pairwise(values))


def test_monotonic_generator_holds_timestamp_during_clock_rollback() -> None:
    timestamps = iter([2_000, 1_999, 1_500, 2_001])
    random_values = iter([100, 0])
    generator = MonotonicUlidGenerator(
        clock=lambda: next(timestamps),
        random_source=lambda _bits: next(random_values),
    )

    values = [generator() for _ in range(4)]

    assert [value.timestamp_ms for value in values] == [2_000, 2_000, 2_000, 2_001]
    assert [value.randomness for value in values] == [100, 101, 102, 0]
    assert values == sorted(values)


def test_monotonic_generator_reaches_random_limit_then_fails_without_wraparound() -> None:
    generator = MonotonicUlidGenerator(
        clock=_constant_clock(8_000),
        random_source=_constant_random(MAX_ULID_RANDOMNESS - 1),
    )

    before_limit = generator.new()
    at_limit = generator.new()
    with pytest.raises(OverflowError, match="random space exhausted"):
        generator.new()

    assert before_limit.randomness == MAX_ULID_RANDOMNESS - 1
    assert at_limit.randomness == MAX_ULID_RANDOMNESS
    assert before_limit < at_limit


@pytest.mark.parametrize(
    ("clock_value", "random_value"),
    [(-1, 0), (MAX_ULID_TIMESTAMP + 1, 0), (True, 0), (0, -1), (0, 1 << 80), (0, False)],
)
def test_monotonic_generator_rejects_invalid_sources(
    clock_value: object,
    random_value: object,
) -> None:
    generator = MonotonicUlidGenerator(
        clock=lambda: clock_value,
        random_source=lambda _bits: random_value,
    )

    with pytest.raises(InvalidDomainIdentifier):
        generator.new()


def test_default_generator_uses_secrets_randbits_and_custom_source_is_isolated() -> None:
    with patch.object(secrets, "randbits", return_value=77) as secure_random:
        secure_generator = MonotonicUlidGenerator(clock=_constant_clock(5_000))
        generated = secure_generator.new()

    custom_generator = MonotonicUlidGenerator(
        clock=_constant_clock(5_000),
        random_source=_constant_random(88),
    )

    assert generated.randomness == 77
    secure_random.assert_called_once_with(80)
    assert custom_generator.new().randomness == 88
    assert new_ulid() != custom_generator.new()


def test_monotonic_generator_is_unique_across_threads() -> None:
    generator = MonotonicUlidGenerator(
        clock=_constant_clock(50_000),
        random_source=_constant_random(0),
    )

    with ThreadPoolExecutor(max_workers=12) as executor:
        values = list(executor.map(lambda _index: generator.new(), range(20_000)))

    assert len(set(values)) == 20_000
    ordered = sorted(values)
    assert all(left < right for left, right in pairwise(ordered))
    assert all(len(str(value)) == 26 for value in values)


def test_one_hundred_thousand_generated_ulids_are_unique_and_parseable() -> None:
    generator = MonotonicUlidGenerator(
        clock=_constant_clock(75_000),
        random_source=_constant_random(0),
    )
    encoded: set[str] = set()

    for _ in range(100_000):
        text = str(generator.new())
        assert Ulid.parse(text).timestamp_ms == 75_000
        encoded.add(text)

    assert len(encoded) == 100_000


@pytest.mark.parametrize(
    "prefix",
    ["a", "abcdefghijkl0", "UP", "1x", "a_b", "a-1", "a ", "api", "system"],
)
def test_prefixed_ulid_rejects_invalid_or_reserved_prefixes(prefix: str) -> None:
    with pytest.raises(InvalidDomainIdentifier):
        PrefixedUlid(prefix, Ulid.from_int(1))


def test_prefixed_ulid_constructs_parses_sorts_hashes_and_normalizes() -> None:
    low = PrefixedUlid("rev", Ulid.from_int(1))
    high = PrefixedUlid("rev", Ulid.from_int(2))
    other_prefix = PrefixedUlid("tst", Ulid.from_int(0))
    parsed = PrefixedUlid.parse(f"rev_{KNOWN_ULID.lower()}")

    assert parsed.prefix == "rev"
    assert parsed.ulid == Ulid.parse(KNOWN_ULID)
    assert str(parsed) == f"rev_{KNOWN_ULID}"
    assert repr(parsed) == f"PrefixedUlid('rev_{KNOWN_ULID}')"
    assert sorted([other_prefix, high, low]) == [low, high, other_prefix]
    assert {low: "value"}[PrefixedUlid.parse(str(low))] == "value"
    assert low != "rev_00000000000000000000000001"
    with pytest.raises(TypeError):
        _ = low < object()


def test_prefixed_ulid_constructor_rejects_a_non_ulid_component() -> None:
    with pytest.raises(InvalidDomainIdentifier):
        PrefixedUlid("tst", "not-a-ulid")


@pytest.mark.parametrize(
    "text",
    [
        KNOWN_ULID,
        f"tst__{KNOWN_ULID}",
        f"TST_{KNOWN_ULID}",
        f"1st_{KNOWN_ULID}",
        f"a_{KNOWN_ULID}",
        f"abcdefghijklm_{KNOWN_ULID}",
    ],
)
def test_prefixed_ulid_rejects_invalid_complete_text_without_echo(text: str) -> None:
    with pytest.raises(InvalidDomainIdentifier) as captured:
        PrefixedUlid.parse(text)

    assert text not in str(captured.value)


def test_concrete_prefixed_types_are_fixed_immutable_and_not_interchangeable() -> None:
    TstId = create_prefixed_ulid_type("TstId", "tst")
    RevId = create_prefixed_ulid_type("RevId", "rev")
    ulid = Ulid.parse(KNOWN_ULID)
    test_id = TstId.from_ulid(ulid)
    revision_id = RevId.from_ulid(ulid)

    assert test_id.prefix == "tst"
    assert test_id.ulid == ulid
    assert str(test_id) == f"tst_{KNOWN_ULID}"
    assert repr(test_id) == f"TstId('tst_{KNOWN_ULID}')"
    assert TstId.parse(str(test_id)) == test_id
    assert test_id != revision_id
    assert len({test_id, revision_id}) == 2
    with pytest.raises(InvalidDomainIdentifier):
        TstId.parse(str(revision_id))
    with pytest.raises(AttributeError, match="immutable"):
        test_id.prefix = "rev"


def test_identifiers_require_explicit_serialization() -> None:
    ulid = Ulid.from_int(1)
    prefixed = PrefixedUlid("tst", ulid)

    with pytest.raises(ValueError):
        jsonable_encoder(ulid)
    with pytest.raises(ValueError):
        jsonable_encoder(prefixed)

    assert str(ulid) == "00000000000000000000000001"
    assert str(prefixed) == "tst_00000000000000000000000001"


def test_concrete_prefixed_type_new_uses_injected_generator() -> None:
    TstId = create_prefixed_ulid_type("TstId", "tst")
    generator = MonotonicUlidGenerator(
        clock=_constant_clock(123_456),
        random_source=_constant_random(9),
    )

    first = TstId.new(generator)
    second = TstId.new(generator)
    process_generated = TstId.new()

    assert isinstance(first, TstId)
    assert first.prefix == "tst"
    assert first.ulid.timestamp_ms == 123_456
    assert first < second
    assert TstId.parse(str(process_generated)) == process_generated


def test_concrete_prefixed_type_rejects_a_non_ulid_component() -> None:
    TstId = create_prefixed_ulid_type("TstId", "tst")

    with pytest.raises(InvalidDomainIdentifier):
        TstId.from_ulid("not-a-ulid")


def test_concrete_type_ordering_uses_only_prefix_and_ulid() -> None:
    AlphaId = create_prefixed_ulid_type("AlphaId", "tst")
    BetaId = create_prefixed_ulid_type("BetaId", "tst")
    ulid = Ulid.from_int(1)
    alpha = AlphaId.from_ulid(ulid)
    beta = BetaId.from_ulid(ulid)

    assert alpha != beta
    assert not alpha < beta
    assert not beta < alpha
    ordered = sorted([beta, alpha])
    assert ordered[0] is beta
    assert ordered[1] is alpha


def test_repeated_concrete_type_declarations_remain_distinct() -> None:
    FirstId = create_prefixed_ulid_type("RepeatedId", "tst")
    SecondId = create_prefixed_ulid_type("RepeatedId", "tst")
    ulid = Ulid.from_int(1)
    first = FirstId.from_ulid(ulid)
    second = SecondId.from_ulid(ulid)

    assert FirstId is not SecondId
    assert first != second
    assert len({first, second}) == 2


def test_factory_result_exposes_statically_declared_concrete_type_operations() -> None:
    identifier_type: type[PrefixedUlid] = create_prefixed_ulid_type("TypedId", "tst")
    generator = MonotonicUlidGenerator(
        clock=_constant_clock(123_456),
        random_source=_constant_random(10),
    )

    from_existing: PrefixedUlid = identifier_type.from_ulid(Ulid.from_int(1))
    generated: PrefixedUlid = identifier_type.new(generator)

    assert from_existing == identifier_type.parse(str(from_existing))
    assert generated.ulid == Ulid.from_parts(123_456, 10)


def test_concrete_type_constructor_enforces_its_fixed_prefix() -> None:
    TstId = create_prefixed_ulid_type("TstId", "tst")

    with pytest.raises(TypeError):
        TstId("rev", Ulid.from_int(1))


def test_concrete_type_prefix_cannot_be_changed_through_a_class_attribute() -> None:
    TstId = create_prefixed_ulid_type("TstId", "tst")
    ulid = Ulid.from_int(1)

    type.__setattr__(TstId, "_fixed_prefix", "rev")
    try:
        assert str(TstId.from_ulid(ulid)) == "tst_00000000000000000000000001"
        with pytest.raises(InvalidDomainIdentifier):
            TstId.parse("rev_00000000000000000000000001")
    finally:
        type.__delattr__(TstId, "_fixed_prefix")


@pytest.mark.parametrize(
    ("type_name", "prefix"),
    [("", "tst"), ("lowerId", "tst"), ("Bad_Name", "tst"), ("TstId", "api")],
)
def test_concrete_type_factory_rejects_invalid_declarations(type_name: str, prefix: str) -> None:
    with pytest.raises(InvalidDomainIdentifier):
        create_prefixed_ulid_type(type_name, prefix)


def test_test_only_prefixes_and_future_business_types_are_absent_from_production() -> None:
    create_prefixed_ulid_type("TstId", "tst")
    production_names = vars(identifiers_module)

    assert "TstId" not in production_names
    assert "RevId" not in production_names
    assert "ProjectId" not in production_names
    assert "ChapterId" not in production_names
    source = Path(identifiers_module.__file__).read_text(encoding="utf-8")
    assert "ProjectId =" not in source
    assert "ChapterId =" not in source


@pytest.mark.parametrize(
    ("expected", "actual"),
    [(0, 1), (1, 0), (True, 1), (1, False), ("1", 1), (1, 1.5)],
)
def test_concurrency_conflict_rejects_unsafe_structured_fields(
    expected: object,
    actual: object,
) -> None:
    with pytest.raises(InvalidConcurrencyVersion):
        ConcurrencyConflict(expected_version=expected, actual_version=actual)
