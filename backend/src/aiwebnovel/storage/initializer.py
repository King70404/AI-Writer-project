"""Explicit, idempotent creation and validation of managed directories."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from aiwebnovel.storage.paths import StoragePaths

ReparsePointDetector = Callable[[Path], bool]


class StorageInitializationError(RuntimeError):
    """Raised with a path-free message when the managed layout is unsafe."""


@dataclass(frozen=True, slots=True)
class StorageInitializationResult:
    """Safe initialization counts without exposing local paths."""

    created_directories: int
    total_directories: int


def is_reparse_point(path: Path) -> bool:
    """Detect symbolic links and Windows reparse points without following them."""
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StorageInitializationError("Storage path attributes could not be inspected") from exc

    if stat.S_ISLNK(path_stat.st_mode):
        return True
    if os.name != "nt":
        return False

    attributes = int(getattr(path_stat, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & reparse_flag)


def _inspect_directory(path: Path, detector: ReparsePointDetector) -> bool:
    """Return existence after rejecting non-directories and redirections."""
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise StorageInitializationError("Storage directory could not be inspected") from exc

    try:
        redirected = detector(path)
    except StorageInitializationError:
        raise
    except OSError as exc:
        raise StorageInitializationError("Storage path attributes could not be inspected") from exc
    if redirected:
        raise StorageInitializationError("Storage directories must not be reparse points")
    if not path.is_dir():
        raise StorageInitializationError("A required storage directory is not a directory")
    return True


def validate_storage_layout(
    paths: StoragePaths,
    *,
    reparse_detector: ReparsePointDetector | None = None,
) -> None:
    """Verify every standard directory exists and remains a real directory."""
    detector = reparse_detector or is_reparse_point
    for directory in paths.directories:
        if not _inspect_directory(directory, detector):
            raise StorageInitializationError("A required storage directory is missing")


def initialize_storage(
    paths: StoragePaths,
    *,
    reparse_detector: ReparsePointDetector | None = None,
) -> StorageInitializationResult:
    """Create the fixed directory layout without files, deletion, or ACL changes."""
    detector = reparse_detector or is_reparse_point
    created_count = 0

    for directory in paths.directories:
        if _inspect_directory(directory, detector):
            continue
        try:
            directory.mkdir(exist_ok=False)
            created_count += 1
        except FileExistsError:
            pass
        except OSError as exc:
            raise StorageInitializationError("A storage directory could not be created") from exc

        if not _inspect_directory(directory, detector):
            raise StorageInitializationError("A storage directory was not created")

    return StorageInitializationResult(
        created_directories=created_count,
        total_directories=len(paths.directories),
    )
