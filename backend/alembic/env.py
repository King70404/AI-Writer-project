"""Alembic environment driven by validated AIWebNovel settings."""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

backend_root = Path(__file__).resolve().parents[1]
source_root = backend_root / "src"
if str(source_root) not in sys.path:
    sys.path.insert(0, str(source_root))

from aiwebnovel.core.config import get_settings  # noqa: E402
from aiwebnovel.db.engine import (  # noqa: E402
    create_database_engine,
    resolve_database_url,
)
from aiwebnovel.db.model_registry import load_model_metadata  # noqa: E402
from aiwebnovel.storage.initializer import initialize_storage  # noqa: E402
from aiwebnovel.storage.paths import StoragePaths  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = get_settings()
storage_paths = StoragePaths.from_settings(settings)
database_url = resolve_database_url(settings, storage_paths)
target_metadata = load_model_metadata()


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations through the configured synchronous SQLite engine."""
    initialize_storage(storage_paths)
    engine = create_database_engine(
        settings,
        database_url,
        storage_paths=storage_paths,
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
