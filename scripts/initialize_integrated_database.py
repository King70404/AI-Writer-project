"""Initialize an absent user database once; never migrate or replace existing data."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from aiwebnovel.core.config import get_settings
from aiwebnovel.storage.initializer import initialize_storage
from aiwebnovel.storage.paths import StoragePaths


def initialize_database() -> bool:
    """Claim a new database exclusively, leaving existing files completely untouched."""
    paths = StoragePaths.from_settings(get_settings())
    initialize_storage(paths)
    try:
        with paths.database_file.open("xb"):
            pass
    except FileExistsError:
        return False
    # A failed first migration remains for inspection; it is never deleted or retried
    # implicitly on the next launch. Existing database migrations stay operator-owned.
    configuration = Config(
        str(Path(__file__).resolve().parents[1] / "backend/alembic.ini")
    )
    command.upgrade(configuration, "head")
    return True


if __name__ == "__main__":
    initialize_database()
