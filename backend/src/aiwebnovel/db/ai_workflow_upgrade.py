"""Explicit, backed-up upgrade of one managed legacy author database."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine
from sqlalchemy.exc import DBAPIError

from aiwebnovel.db.author_schema import (
    CURRENT_REVISION,
    SUPPORTED_SCHEMA_TABLES,
    TABLE_QUERY,
)
from aiwebnovel.db.model_registry import load_model_metadata
from aiwebnovel.storage.paths import StoragePaths

_TARGET_REVISION = CURRENT_REVISION
# The backup and restore checks recognize the same revisions as this upgrade.
_SCHEMA_TABLES = SUPPORTED_SCHEMA_TABLES
_TABLE_QUERY = TABLE_QUERY


class AIWorkflowUpgradeFailed(RuntimeError):
    """An upgrade failed without revealing database paths or contents."""


class AIWorkflowUpgradeUnsupported(AIWorkflowUpgradeFailed):
    """Only a recognized, managed database may use the in-app upgrade."""


class AIWorkflowUpgradeBusy(AIWorkflowUpgradeFailed):
    """Another database writer prevented obtaining a consistent backup."""


@dataclass(frozen=True, slots=True)
class StorageUpgradeChecks:
    """Mandatory storage safety operations supplied by the composition root."""

    validate_layout: Callable[[StoragePaths], None]
    is_reparse_point: Callable[[Path], bool]


def _validate_paths(engine: Engine, paths: StoragePaths, checks: StorageUpgradeChecks) -> None:
    if (
        engine.dialect.name != "sqlite"
        or not engine.url.database
        or engine.url.query
        or os.path.normcase(os.path.abspath(engine.url.database))
        != os.path.normcase(os.fspath(paths.database_file))
    ):
        raise AIWorkflowUpgradeUnsupported("Only the managed database can be upgraded")
    try:
        checks.validate_layout(paths)
    except Exception:  # noqa: BLE001 - storage adapters never expose paths through this API.
        raise AIWorkflowUpgradeUnsupported("The managed database layout is unsafe") from None
    inspected = (
        *paths.root.parents,
        paths.database_file,
        *(Path(f"{paths.database_file}{suffix}") for suffix in ("-wal", "-shm", "-journal")),
    )
    if (
        any(checks.is_reparse_point(path) for path in inspected)
        or not paths.database_file.is_file()
    ):
        raise AIWorkflowUpgradeUnsupported("The managed database layout is unsafe")


def _check_schema(connection: Connection) -> str:
    tables = frozenset(connection.exec_driver_sql(_TABLE_QUERY).scalars())
    if "alembic_version" not in tables:
        raise AIWorkflowUpgradeUnsupported("The database version is not supported")
    versions = list(connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalars())
    if len(versions) != 1 or versions[0] not in _SCHEMA_TABLES:
        raise AIWorkflowUpgradeUnsupported("The database version or tables are not supported")
    revision = str(versions[0])
    expected_tables = _SCHEMA_TABLES[revision]
    if tables != expected_tables | {"alembic_version"}:
        raise AIWorkflowUpgradeUnsupported("The database version or tables are not supported")
    metadata = load_model_metadata()
    for table in sorted(expected_tables):
        columns = {row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")')}
        if columns != set(metadata.tables[table].columns.keys()):
            raise AIWorkflowUpgradeUnsupported("The existing author schema is incomplete")
    return revision


def _backup_progress(status: int, _remaining: int, _total: int) -> None:
    if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        raise AIWorkflowUpgradeBusy("The database is busy; no upgrade was applied")


def _create_verified_backup(
    paths: StoragePaths, checks: StorageUpgradeChecks, revision: str
) -> None:
    """Read committed WAL state on a separate connection while the writer is reserved."""
    checks.validate_layout(paths)
    backup = paths.backups / f"before-ai-workflow-{uuid4().hex}.sqlite3"
    # Exclusive creation prevents overwriting any previous recovery copy.
    with backup.open("xb"):
        pass
    if checks.is_reparse_point(backup):
        raise AIWorkflowUpgradeFailed("The backup location is unsafe")
    with (
        closing(sqlite3.connect(paths.database_file.as_uri() + "?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(backup.as_uri() + "?mode=rw", uri=True)) as destination,
    ):
        source.backup(destination, pages=256, progress=_backup_progress, sleep=0)
        if destination.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise AIWorkflowUpgradeFailed("The recovery copy did not pass integrity verification")
        tables = {row[0] for row in destination.execute(_TABLE_QUERY)}
        if tables != _SCHEMA_TABLES[revision] | {"alembic_version"} or destination.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchall() != [(revision,)]:
            raise AIWorkflowUpgradeFailed("The recovery copy has an unexpected schema")
    # Windows _commit (used by os.fsync) requires a writable file descriptor.
    with backup.open("r+b") as recovery_file:
        os.fsync(recovery_file.fileno())


def _migrate(connection: Connection) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[3] / "alembic"))
    config.attributes["connection"] = connection
    command.upgrade(config, _TARGET_REVISION)


def upgrade_ai_workflow_database(
    engine: Engine, storage_paths: StoragePaths, checks: StorageUpgradeChecks
) -> None:
    """Back up a supported 0006/0007 database and atomically upgrade on author request.

    The caller serializes in-process upgrade requests. No path or connection is
    selected from environment variables. A ready 0008 database is a no-op. Failed
    upgrades retain any recovery copy and never replace the author's database.
    """
    try:
        _validate_paths(engine, storage_paths, checks)
        with engine.connect() as connection:
            # This SQL BEGIN, before any inspection, makes SQLite DDL transactional
            # and excludes other writers until both the backup and migration finish.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                revision = _check_schema(connection)
                if revision == _TARGET_REVISION:
                    connection.rollback()
                    return
                _create_verified_backup(storage_paths, checks, revision)
                _migrate(connection)
                if _check_schema(connection) != _TARGET_REVISION:
                    raise AIWorkflowUpgradeFailed("The upgraded schema did not pass verification")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    except AIWorkflowUpgradeFailed:
        raise
    except (sqlite3.Error, DBAPIError) as exc:
        original = exc.orig if isinstance(exc, DBAPIError) else exc
        if getattr(original, "sqlite_errorcode", 0) & 0xFF in (
            sqlite3.SQLITE_BUSY,
            sqlite3.SQLITE_LOCKED,
        ):
            raise AIWorkflowUpgradeBusy("The database is busy; no upgrade was applied") from None
        raise AIWorkflowUpgradeFailed(
            "The database upgrade failed; the original data is retained"
        ) from None
    except Exception:  # noqa: BLE001 - callers only receive a path- and content-free failure.
        raise AIWorkflowUpgradeFailed(
            "The database upgrade failed; the original data is retained"
        ) from None
