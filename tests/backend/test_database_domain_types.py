"""Persistence-boundary tests for reusable domain value objects."""

import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import Column, Engine, Integer, MetaData, Table, create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import SAWarning, StatementError

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import (
    ConcurrencyVersionType,
    PrefixedUlidType,
    RevisionNumberType,
    UlidType,
    UtcDateTimeType,
)
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import (
    InvalidConcurrencyVersion,
    InvalidDomainIdentifier,
    InvalidRevisionNumber,
)
from aiwebnovel.domain.identifiers import PrefixedUlid, Ulid, create_prefixed_ulid_type
from aiwebnovel.domain.revisions import RevisionNumber

pytestmark = pytest.mark.integration

_KNOWN_ULID_TEXT = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
_TestIdentifier = create_prefixed_ulid_type("DatabaseTestIdentifier", "tst")
_OtherIdentifier = create_prefixed_ulid_type("OtherDatabaseTestIdentifier", "oth")


@dataclass(frozen=True, slots=True)
class _DatabaseHarness:
    engine: Engine
    metadata: MetaData
    table: Table
    path: Path


def _remove_sqlite_artifacts(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


@pytest.fixture
def domain_type_database(tmp_path: Path) -> Iterator[_DatabaseHarness]:
    database_path = tmp_path / "domain-types.sqlite3"
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=database_path.as_posix()),
        pool_pre_ping=True,
    )
    metadata = MetaData()
    formal_tables_before = frozenset(Base.metadata.tables)
    table = Table(
        "domain_type_values",
        metadata,
        Column("record_key", Integer, primary_key=True),
        Column("ulid_value", UlidType(), nullable=True),
        Column("prefixed_value", PrefixedUlidType(_TestIdentifier), nullable=True),
        Column("base_prefixed_value", PrefixedUlidType(), nullable=True),
        Column("revision_value", RevisionNumberType(), nullable=True),
        Column("concurrency_value", ConcurrencyVersionType(), nullable=True),
        Column("utc_value", UtcDateTimeType(), nullable=True),
    )

    assert "domain_type_values" not in Base.metadata.tables
    assert table.metadata is metadata
    assert metadata is not Base.metadata
    try:
        metadata.create_all(engine)
        yield _DatabaseHarness(engine, metadata, table, database_path)
    finally:
        engine.dispose()
        _remove_sqlite_artifacts(database_path)
        assert frozenset(Base.metadata.tables) == formal_tables_before
        assert not any(
            Path(f"{database_path}{suffix}").exists() for suffix in ("", "-wal", "-shm", "-journal")
        )


def test_adapters_declare_bounded_storage_and_cache_safety(
    domain_type_database: _DatabaseHarness,
) -> None:
    assert UlidType.cache_ok is True
    assert PrefixedUlidType.cache_ok is True
    assert RevisionNumberType.cache_ok is True
    assert ConcurrencyVersionType.cache_ok is True
    assert UtcDateTimeType.cache_ok is True
    assert UlidType().python_type is Ulid
    assert PrefixedUlidType(_TestIdentifier).python_type is _TestIdentifier
    assert PrefixedUlidType().python_type is PrefixedUlid
    assert RevisionNumberType().python_type is RevisionNumber
    assert ConcurrencyVersionType().python_type is ConcurrencyVersion
    assert UtcDateTimeType().python_type is datetime
    with pytest.raises(TypeError):
        PrefixedUlidType(Ulid)

    with domain_type_database.engine.connect() as connection:
        declared_types = {
            row[1]: row[2]
            for row in connection.exec_driver_sql("PRAGMA table_info(domain_type_values)").all()
        }

    assert declared_types == {
        "record_key": "INTEGER",
        "ulid_value": "TEXT(26)",
        "prefixed_value": "TEXT(39)",
        "base_prefixed_value": "TEXT(39)",
        "revision_value": "INTEGER",
        "concurrency_value": "INTEGER",
        "utc_value": "DATETIME",
    }
    assert "domain_type_values" not in Base.metadata.tables


def test_all_domain_values_round_trip_and_use_primitive_storage(
    domain_type_database: _DatabaseHarness,
) -> None:
    table = domain_type_database.table
    ulid = Ulid.parse(_KNOWN_ULID_TEXT)
    prefixed = _TestIdentifier.from_ulid(ulid)
    base_prefixed = PrefixedUlid("tmp", ulid)
    revision = RevisionNumber(7)
    concurrency = ConcurrencyVersion(9)
    source_time = datetime(
        2026,
        1,
        2,
        12,
        34,
        56,
        123456,
        tzinfo=timezone(timedelta(hours=8)),
    )

    with domain_type_database.engine.begin() as connection:
        connection.execute(
            table.insert().values(
                record_key=1,
                ulid_value=ulid,
                prefixed_value=prefixed,
                base_prefixed_value=base_prefixed,
                revision_value=revision,
                concurrency_value=concurrency,
                utc_value=source_time,
            )
        )

    with domain_type_database.engine.connect() as connection:
        row = connection.execute(select(table).where(table.c.record_key == 1)).one()
        raw = connection.exec_driver_sql(
            "SELECT ulid_value, typeof(ulid_value), "
            "prefixed_value, typeof(prefixed_value), "
            "revision_value, typeof(revision_value), "
            "concurrency_value, typeof(concurrency_value) "
            ", utc_value, typeof(utc_value) "
            "FROM domain_type_values WHERE record_key = 1"
        ).one()

    assert row.ulid_value == ulid
    assert type(row.ulid_value) is Ulid
    assert row.prefixed_value == prefixed
    assert type(row.prefixed_value) is _TestIdentifier
    assert row.base_prefixed_value == base_prefixed
    assert type(row.base_prefixed_value) is PrefixedUlid
    assert row.revision_value == revision
    assert type(row.revision_value) is RevisionNumber
    assert row.concurrency_value == concurrency
    assert type(row.concurrency_value) is ConcurrencyVersion
    assert row.utc_value == datetime(2026, 1, 2, 4, 34, 56, 123456, tzinfo=UTC)
    assert row.utc_value.tzinfo is UTC
    assert raw == (
        _KNOWN_ULID_TEXT,
        "text",
        f"tst_{_KNOWN_ULID_TEXT}",
        "text",
        7,
        "integer",
        9,
        "integer",
        "2026-01-02 04:34:56.123456",
        "text",
    )


def test_null_values_remain_null(domain_type_database: _DatabaseHarness) -> None:
    table = domain_type_database.table
    with domain_type_database.engine.begin() as connection:
        connection.execute(
            table.insert().values(
                record_key=2,
                ulid_value=None,
                prefixed_value=None,
                base_prefixed_value=None,
                revision_value=None,
                concurrency_value=None,
                utc_value=None,
            )
        )

    with domain_type_database.engine.connect() as connection:
        row = connection.execute(
            select(
                table.c.ulid_value,
                table.c.prefixed_value,
                table.c.revision_value,
                table.c.concurrency_value,
                table.c.utc_value,
            ).where(table.c.record_key == 2)
        ).one()

    assert tuple(row) == (None, None, None, None, None)


def test_binding_rejects_primitives_and_crossed_domain_types(
    domain_type_database: _DatabaseHarness,
) -> None:
    table = domain_type_database.table
    ulid = Ulid.parse(_KNOWN_ULID_TEXT)
    wrong_prefixed_type = _OtherIdentifier.from_ulid(ulid)

    invalid_values = (
        {"record_key": 10, "ulid_value": _KNOWN_ULID_TEXT},
        {"record_key": 11, "prefixed_value": f"tst_{_KNOWN_ULID_TEXT}"},
        {"record_key": 12, "prefixed_value": wrong_prefixed_type},
        {"record_key": 13, "revision_value": 1},
        {"record_key": 14, "revision_value": ConcurrencyVersion()},
        {"record_key": 15, "concurrency_value": 1},
        {"record_key": 16, "concurrency_value": RevisionNumber()},
    )

    with domain_type_database.engine.connect() as connection:
        for values in invalid_values:
            with pytest.raises(StatementError) as caught:
                connection.execute(table.insert().values(**values))
            assert type(caught.value.orig) is TypeError

        with pytest.raises(StatementError) as caught:
            connection.execute(
                table.insert().values(
                    record_key=17,
                    utc_value=datetime(2026, 1, 2),
                )
            )
        assert type(caught.value.orig) is ValueError


def test_polluted_values_fail_with_the_matching_domain_error(
    domain_type_database: _DatabaseHarness,
) -> None:
    table = domain_type_database.table
    with domain_type_database.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO domain_type_values "
            "(record_key, ulid_value, prefixed_value, revision_value, concurrency_value) "
            "VALUES (?, ?, ?, ?, ?)",
            (100, "bad\nidentifier", f"oth_{_KNOWN_ULID_TEXT}", 0, -1),
        )

    selections = (
        (table.c.ulid_value, InvalidDomainIdentifier),
        (table.c.prefixed_value, InvalidDomainIdentifier),
        (table.c.revision_value, InvalidRevisionNumber),
        (table.c.concurrency_value, InvalidConcurrencyVersion),
    )
    for column, expected_error in selections:
        with (
            domain_type_database.engine.connect() as connection,
            pytest.raises(expected_error) as caught,
        ):
            connection.execute(select(column).where(table.c.record_key == 100)).scalar_one()
        assert "bad\nidentifier" not in str(caught.value)


def test_polluted_sqlite_storage_classes_are_not_coerced(
    domain_type_database: _DatabaseHarness,
) -> None:
    table = domain_type_database.table
    with domain_type_database.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO domain_type_values "
            "(record_key, ulid_value, prefixed_value, revision_value, concurrency_value) "
            "VALUES (?, ?, ?, ?, ?)",
            (101, b"\x00", b"\x00", "not-an-integer", "not-an-integer"),
        )

    selections = (
        (table.c.ulid_value, InvalidDomainIdentifier),
        (table.c.prefixed_value, InvalidDomainIdentifier),
        (table.c.revision_value, InvalidRevisionNumber),
        (table.c.concurrency_value, InvalidConcurrencyVersion),
    )
    for column, expected_error in selections:
        with (
            domain_type_database.engine.connect() as connection,
            pytest.raises(expected_error),
        ):
            connection.execute(select(column).where(table.c.record_key == 101)).scalar_one()


def test_polluted_datetime_text_is_rejected(domain_type_database: _DatabaseHarness) -> None:
    table = domain_type_database.table
    with domain_type_database.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO domain_type_values (record_key, utc_value) VALUES (?, ?)",
            (102, "not-a-datetime"),
        )

    with domain_type_database.engine.connect() as connection, pytest.raises(ValueError):
        connection.execute(select(table.c.utc_value).where(table.c.record_key == 102)).scalar_one()


def test_repeated_cached_queries_keep_concrete_domain_types_without_warnings(
    domain_type_database: _DatabaseHarness,
) -> None:
    table = domain_type_database.table
    ulid = Ulid.parse(_KNOWN_ULID_TEXT)
    with domain_type_database.engine.begin() as connection:
        connection.execute(
            table.insert().values(
                record_key=200,
                ulid_value=ulid,
                prefixed_value=_TestIdentifier.from_ulid(ulid),
                revision_value=RevisionNumber(3),
                concurrency_value=ConcurrencyVersion(4),
                utc_value=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )

    statement = select(table).where(table.c.record_key == 200)
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always", SAWarning)
        with domain_type_database.engine.connect() as connection:
            rows = [connection.execute(statement).one() for _ in range(4)]

    assert all(type(row.ulid_value) is Ulid for row in rows)
    assert all(type(row.prefixed_value) is _TestIdentifier for row in rows)
    assert all(type(row.revision_value) is RevisionNumber for row in rows)
    assert all(type(row.concurrency_value) is ConcurrencyVersion for row in rows)
    assert all(row.utc_value.tzinfo is UTC for row in rows)
    assert not [warning for warning in caught_warnings if issubclass(warning.category, SAWarning)]
