"""Deterministic readiness checks for the configured SQLite database."""

from dataclasses import dataclass

from sqlalchemy import Engine

from aiwebnovel.db.engine import is_memory_database_url


class DatabaseHealthError(RuntimeError):
    """Raised when a required SQLite readiness invariant is unavailable."""


@dataclass(frozen=True)
class DatabaseHealthResult:
    """Verified SQLite state with no database path or credential content."""

    foreign_keys: bool
    journal_mode: str


def check_database_health(engine: Engine) -> DatabaseHealthResult:
    """Verify connectivity, foreign keys, and file database WAL mode."""
    with engine.connect() as connection:
        if connection.exec_driver_sql("SELECT 1").scalar_one() != 1:
            raise DatabaseHealthError("Database connectivity check failed")

        foreign_keys = int(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one())
        if foreign_keys != 1:
            raise DatabaseHealthError("SQLite foreign keys are not enabled")

        journal_mode = str(connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()).lower()
        if not is_memory_database_url(engine.url) and journal_mode != "wal":
            raise DatabaseHealthError("SQLite WAL mode is not enabled")

    return DatabaseHealthResult(
        foreign_keys=True,
        journal_mode=journal_mode,
    )
