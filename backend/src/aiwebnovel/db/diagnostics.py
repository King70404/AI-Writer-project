"""Public database readiness contract for infrastructure diagnostics."""

from aiwebnovel.core.config import Settings
from aiwebnovel.db.engine import create_database_engine
from aiwebnovel.db.health import check_database_health
from aiwebnovel.storage.paths import StoragePaths


def run_database_diagnostic(settings: Settings, storage_paths: StoragePaths) -> None:
    """Verify the configured SQLite database and always release its engine."""
    engine = create_database_engine(settings, storage_paths=storage_paths)
    try:
        check_database_health(engine)
    finally:
        engine.dispose()
