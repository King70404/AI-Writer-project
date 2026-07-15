"""Local storage paths, initialization, and access verification."""

from aiwebnovel.storage.access import (
    StorageAccessError,
    StorageAccessResult,
    check_storage_access,
    verify_storage_access,
)
from aiwebnovel.storage.health import StorageHealthResult, check_storage_health
from aiwebnovel.storage.initializer import (
    StorageInitializationError,
    StorageInitializationResult,
    initialize_storage,
    is_reparse_point,
    validate_storage_layout,
)
from aiwebnovel.storage.paths import StoragePathError, StoragePaths

__all__ = [
    "StorageAccessError",
    "StorageAccessResult",
    "StorageHealthResult",
    "StorageInitializationError",
    "StorageInitializationResult",
    "StoragePathError",
    "StoragePaths",
    "check_storage_access",
    "check_storage_health",
    "initialize_storage",
    "is_reparse_point",
    "validate_storage_layout",
    "verify_storage_access",
]
