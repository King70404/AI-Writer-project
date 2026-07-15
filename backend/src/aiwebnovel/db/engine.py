"""Synchronous SQLAlchemy engine creation and SQLite connection policy."""

import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import StaticPool

from aiwebnovel.core.config import Settings
from aiwebnovel.storage.paths import StoragePaths

_SUPPORTED_SQLITE_DRIVERS = {"sqlite", "sqlite+pysqlite"}


class DatabaseConfigurationError(ValueError):
    """Raised when database settings are unsupported or malformed."""


def get_sqlite_url(value: str | URL) -> URL:
    """Parse and validate the only database URL family supported in phase 0."""
    try:
        url = value if isinstance(value, URL) else make_url(value)
    except ArgumentError as exc:
        raise DatabaseConfigurationError("database_url must be a valid SQLite URL") from exc

    if url.drivername not in _SUPPORTED_SQLITE_DRIVERS:
        raise DatabaseConfigurationError("Only the SQLite pysqlite driver is supported")
    return url


def is_memory_database_url(value: str | URL) -> bool:
    """Return whether a SQLite URL refers to an in-memory database."""
    url = get_sqlite_url(value)
    mode = url.query.get("mode")
    return url.database in {None, "", ":memory:"} or mode == "memory"


def database_file_path(value: str | URL) -> Path | None:
    """Return the configured SQLite file path, or None for memory databases."""
    url = get_sqlite_url(value)
    if is_memory_database_url(url):
        return None
    if not url.database:
        return None
    return Path(url.database).expanduser()


def resolve_database_url(settings: Settings, storage_paths: StoragePaths) -> URL:
    """Honor an explicit URL or safely derive the default from managed storage."""
    if settings.database_url is not None:
        return get_sqlite_url(settings.database_url)
    return URL.create(
        drivername="sqlite+pysqlite",
        database=storage_paths.database_file.as_posix(),
    )


def ensure_database_parent_directory(value: str | URL) -> Path | None:
    """Create a file database parent only during explicit engine initialization."""
    database_path = database_file_path(value)
    if database_path is None:
        return None
    absolute_path = database_path if database_path.is_absolute() else Path.cwd() / database_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    return absolute_path


def create_database_engine(
    settings: Settings,
    database_url: str | URL | None = None,
    *,
    storage_paths: StoragePaths | None = None,
) -> Engine:
    """Create an unconnected synchronous engine with enforced SQLite PRAGMAs."""
    if database_url is not None:
        url = get_sqlite_url(database_url)
    elif settings.database_url is not None:
        url = get_sqlite_url(settings.database_url)
    elif storage_paths is not None:
        url = resolve_database_url(settings, storage_paths)
    else:
        raise DatabaseConfigurationError(
            "storage_paths is required when database_url is not configured"
        )
    is_memory = is_memory_database_url(url)
    ensure_database_parent_directory(url)

    engine_options: dict[str, object] = {
        "echo": settings.database_echo,
        "pool_pre_ping": True,
        "connect_args": {
            "check_same_thread": False,
            "timeout": settings.database_busy_timeout_ms / 1000,
        },
    }
    if is_memory:
        engine_options["poolclass"] = StaticPool

    engine = create_engine(url, **engine_options)
    busy_timeout_ms = settings.database_busy_timeout_ms

    @event.listens_for(engine, "connect")
    def configure_sqlite_connection(
        dbapi_connection: sqlite3.Connection, _connection_record: object
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
            cursor.execute("PRAGMA foreign_keys = ON")
            if not is_memory:
                cursor.execute("PRAGMA journal_mode = WAL")
                journal_mode_row = cursor.fetchone()
                journal_mode = str(journal_mode_row[0]).lower() if journal_mode_row else ""
                if journal_mode != "wal":
                    raise sqlite3.OperationalError("SQLite WAL mode could not be enabled")
            cursor.execute("PRAGMA synchronous = NORMAL")
        finally:
            cursor.close()

    return engine
