"""Storage readiness assembled from layout and live access verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aiwebnovel.storage.access import StorageAccessResult, verify_storage_access
from aiwebnovel.storage.initializer import validate_storage_layout
from aiwebnovel.storage.paths import StoragePaths


@dataclass(frozen=True, slots=True)
class StorageHealthResult:
    """One successful storage readiness result with no filesystem paths."""

    status: Literal["ok"]
    access: StorageAccessResult


def check_storage_health(paths: StoragePaths) -> StorageHealthResult:
    """Recheck the managed layout and current-process access capabilities."""
    validate_storage_layout(paths)
    return StorageHealthResult(status="ok", access=verify_storage_access(paths))
