"""Compose the backup service from validated settings and storage safety checks."""

import os

from aiwebnovel.backup.service import AuthorBackupService, BackupStorageChecks, BackupUnavailable
from aiwebnovel.core.config import Settings
from aiwebnovel.db.engine import database_file_path
from aiwebnovel.storage.initializer import (
    initialize_storage,
    is_reparse_point,
    validate_storage_layout,
)
from aiwebnovel.storage.paths import StoragePaths


def compose_backup_service(settings: Settings, paths: StoragePaths) -> AuthorBackupService:
    """Bind backups to the managed database of exactly one data root.

    A development or test database URL that points anywhere else disables backups,
    so no request can back up or restore an unmanaged database.
    """
    if settings.database_url is not None:
        configured = database_file_path(settings.database_url)
        if configured is None or os.path.normcase(os.path.abspath(configured)) != os.path.normcase(
            os.fspath(paths.database_file)
        ):
            raise BackupUnavailable("Backups only support the managed database")
    return AuthorBackupService(
        paths,
        BackupStorageChecks(validate_storage_layout, is_reparse_point, initialize_storage),
        app_version=settings.app_version,
    )
