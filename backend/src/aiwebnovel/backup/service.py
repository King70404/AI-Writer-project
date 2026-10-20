"""Author backup management and restore into a brand-new data root.

The service only ever reads the managed author database. Backups are written to
the managed ``backups`` directory under an exclusive temporary name, verified,
then renamed into place. Restore never targets the current data root: it creates
an independent data root in a new or empty directory, copies the verified
snapshot there and verifies the restored copy again.
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Literal

from aiwebnovel.backup.archive import (
    ARCHIVE_NAME_PATTERN,
    DEFAULT_MAX_DATABASE_BYTES,
    BackupArchiveError,
    BackupCorrupt,
    BackupManifest,
    DatabaseSummary,
    archive_name,
    check_sqlite_file,
    extract_and_verify,
    file_sha256,
    is_backup_id,
    read_manifest,
    snapshot_database,
    write_archive,
)
from aiwebnovel.core.config import normalize_data_root
from aiwebnovel.storage.paths import StoragePaths

MAX_LISTED_BACKUPS = 200
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_TARGET_NAME_PATTERN = re.compile(r"\A[\w](?:[\w.-]{0,62}[\w])?\Z")
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


class BackupServiceError(RuntimeError):
    """Base class; messages never contain local paths or author content."""

    code = "BACKUP_FAILED"


class BackupUnavailable(BackupServiceError):
    code = "BACKUP_UNAVAILABLE"


class BackupBusy(BackupServiceError):
    code = "BACKUP_BUSY"


class BackupNotFound(BackupServiceError):
    code = "BACKUP_NOT_FOUND"


class RestoreTargetInvalid(BackupServiceError):
    code = "RESTORE_TARGET_INVALID"


class RestoreTargetNotEmpty(BackupServiceError):
    code = "RESTORE_TARGET_NOT_EMPTY"


@dataclass(frozen=True, slots=True)
class BackupStorageChecks:
    """Storage safety operations supplied by the composition root."""

    validate_layout: Callable[[StoragePaths], None]
    is_reparse_point: Callable[[Path], bool]
    initialize: Callable[[StoragePaths], object]


@dataclass(frozen=True, slots=True)
class BackupListing:
    backup_id: str
    file_bytes: int
    manifest: BackupManifest | None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    backup_id: str
    status: Literal["valid", "corrupt", "incompatible"]
    problem: str | None
    manifest: BackupManifest | None


@dataclass(frozen=True, slots=True)
class RestoreResult:
    backup_id: str
    target_root: Path
    summary: DatabaseSummary


def validate_target_name(name: str) -> str:
    """Accept one plain folder name that is safe on Windows and POSIX."""
    normalized = unicodedata.normalize("NFC", name)
    if (
        normalized != name
        or _TARGET_NAME_PATTERN.fullmatch(name) is None
        or name.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
    ):
        raise RestoreTargetInvalid("Use a plain new folder name for the restored copy")
    return name


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.fspath(left)) == os.path.normcase(os.fspath(right))


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        common = os.path.commonpath((os.fspath(root), os.fspath(candidate)))
    except ValueError:
        return False
    return _same_path(Path(common), root)


def _utc_stamp(now: datetime) -> tuple[str, str]:
    moment = now.astimezone(UTC).replace(microsecond=0)
    return moment.strftime("%Y%m%dT%H%M%SZ"), moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _busy_progress(status: int, _remaining: int, _total: int) -> None:
    if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        raise BackupBusy("The database is busy; no backup was created")


class AuthorBackupService:
    """Create, list, verify, download and restore author backups for one data root."""

    def __init__(
        self,
        paths: StoragePaths,
        checks: BackupStorageChecks,
        *,
        app_version: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        token: Callable[[], str] = lambda: secrets.token_hex(6),
        max_database_bytes: int = DEFAULT_MAX_DATABASE_BYTES,
    ) -> None:
        self._paths = paths
        self._checks = checks
        self._app_version = app_version
        self._clock = clock
        self._token = token
        self._max_database_bytes = max_database_bytes
        self._lock = Lock()

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        if not self._lock.acquire(blocking=False):
            raise BackupBusy("Another backup operation is running")
        try:
            yield
        finally:
            self._lock.release()

    def _redirected(self, path: Path) -> bool:
        try:
            return self._checks.is_reparse_point(path)
        except Exception:  # noqa: BLE001 - an uninspectable path is treated as unsafe.
            return True

    def _validate_source(self) -> None:
        paths = self._paths
        try:
            self._checks.validate_layout(paths)
        except Exception:  # noqa: BLE001 - storage failures never expose paths.
            raise BackupUnavailable("The managed data layout is unsafe") from None
        inspected = (
            *paths.root.parents,
            paths.backups,
            paths.runtime_temp,
            paths.database_file,
            *(Path(f"{paths.database_file}{suffix}") for suffix in _SIDECAR_SUFFIXES),
        )
        if any(self._redirected(path) for path in inspected) or not paths.database_file.is_file():
            raise BackupUnavailable("The managed database is unavailable")

    def _archive_path(self, backup_id: str) -> Path:
        if not is_backup_id(backup_id):
            raise BackupNotFound("The backup does not exist")
        path = self._paths.backups / archive_name(backup_id)
        if self._redirected(path) or not path.is_file():
            raise BackupNotFound("The backup does not exist")
        return path

    @contextmanager
    def _temporary_file(self, label: str) -> Iterator[Path]:
        path = self._paths.runtime_temp / f".{label}-{secrets.token_hex(12)}.tmp"
        try:
            yield path
        finally:
            for suffix in ("", *_SIDECAR_SUFFIXES):
                Path(f"{path}{suffix}").unlink(missing_ok=True)

    def create(self) -> BackupListing:
        """Write one consistent, verified backup of the live database."""
        with self._exclusive():
            self._validate_source()
            stamp, created_at = _utc_stamp(self._clock())
            backup_id = f"{stamp}-{self._token()}"
            final = self._paths.backups / archive_name(backup_id)
            partial = self._paths.backups / f".{final.name}.partial"
            try:
                with self._temporary_file("backup-snapshot") as snapshot:
                    snapshot_database(self._paths.database_file, snapshot, progress=_busy_progress)
                    summary = check_sqlite_file(snapshot, immutable=True)
                    sha256, size = file_sha256(snapshot)
                    manifest = BackupManifest(
                        backup_id=backup_id,
                        created_at=created_at,
                        app_version=self._app_version,
                        database_sha256=sha256,
                        database_bytes=size,
                        summary=summary,
                    )
                    write_archive(partial, manifest, snapshot)
                with self._temporary_file("backup-verify") as verified:
                    extract_and_verify(
                        partial,
                        backup_id,
                        verified,
                        max_database_bytes=self._max_database_bytes,
                    )
                if final.exists() or self._redirected(final):
                    raise BackupServiceError("The backup name is already in use")
                os.replace(partial, final)
                size = final.stat().st_size
            except BackupServiceError:
                raise
            except BackupArchiveError as exc:
                raise BackupServiceError(
                    f"The backup did not pass verification ({exc.code})"
                ) from None
            except (OSError, sqlite3.Error):
                raise BackupServiceError("The backup could not be written") from None
            finally:
                partial.unlink(missing_ok=True)
            return BackupListing(backup_id, size, manifest)

    def list(self) -> tuple[BackupListing, ...]:
        """List archives newest first, reading only their manifests."""
        self._validate_source()
        listings: list[BackupListing] = []
        with os.scandir(self._paths.backups) as entries:
            names = sorted(
                (entry.name for entry in entries if ARCHIVE_NAME_PATTERN.fullmatch(entry.name)),
                reverse=True,
            )
        for name in names[:MAX_LISTED_BACKUPS]:
            match = ARCHIVE_NAME_PATTERN.fullmatch(name)
            assert match is not None
            backup_id = match.group(1)
            try:
                path = self._archive_path(backup_id)
                size = path.stat().st_size
            except (BackupNotFound, OSError):
                continue
            try:
                manifest: BackupManifest | None = read_manifest(path, backup_id)
            except BackupArchiveError:
                manifest = None
            listings.append(BackupListing(backup_id, size, manifest))
        return tuple(listings)

    def verify(self, backup_id: str) -> VerificationResult:
        """Fully verify one archive, reporting damage as a result instead of an error."""
        with self._exclusive():
            self._validate_source()
            path = self._archive_path(backup_id)
            try:
                with self._temporary_file("backup-verify") as extracted:
                    manifest = extract_and_verify(
                        path,
                        backup_id,
                        extracted,
                        max_database_bytes=self._max_database_bytes,
                    )
            except BackupArchiveError as exc:
                if exc.code == "BACKUP_INCOMPATIBLE":
                    return VerificationResult(backup_id, "incompatible", exc.code, None)
                return VerificationResult(backup_id, "corrupt", exc.code, None)
            except OSError:
                raise BackupServiceError("The backup could not be verified") from None
            return VerificationResult(backup_id, "valid", None, manifest)

    def download_path(self, backup_id: str) -> Path:
        """Return the archive path for streaming after a manifest sanity check."""
        self._validate_source()
        path = self._archive_path(backup_id)
        try:
            read_manifest(path, backup_id)
        except BackupArchiveError as exc:
            raise BackupCorrupt(str(exc)) from None
        return path

    def restore_to_sibling(self, backup_id: str, target_name: str) -> RestoreResult:
        """Restore into a new folder next to the current data root (HTTP entry)."""
        name = validate_target_name(target_name)
        parent = self._paths.root.parent
        return self.restore(backup_id, parent / name, allowed_parent=parent)

    def _validate_target(self, raw_target: Path, allowed_parent: Path | None) -> Path:
        try:
            target = normalize_data_root(raw_target)
            target_paths = StoragePaths.from_root(target)
        except ValueError:
            raise RestoreTargetInvalid("The restore folder must be an absolute path") from None
        current = self._paths.root
        if _is_within(current, target) or _is_within(target, current):
            raise RestoreTargetInvalid("The restore folder must be outside the current data")
        if allowed_parent is not None and not _same_path(target.parent, allowed_parent):
            raise RestoreTargetInvalid("The restore folder is outside the allowed location")
        if any(self._redirected(path) for path in (target, *target.parents)):
            raise RestoreTargetInvalid("The restore folder location is unsafe")
        if not target.parent.is_dir():
            raise RestoreTargetInvalid("The restore folder's parent does not exist")
        if target.exists() or target.is_symlink():
            if not target.is_dir():
                raise RestoreTargetNotEmpty("The restore folder already exists")
            with os.scandir(target) as entries:
                if next(entries, None) is not None:
                    raise RestoreTargetNotEmpty("The restore folder is not empty")
        return target_paths.root

    def restore(
        self,
        backup_id: str,
        target_root: Path,
        *,
        allowed_parent: Path | None = None,
    ) -> RestoreResult:
        """Verify a backup, then build an independent data root from it.

        The current data root is never written. The target must be a new folder or
        an existing empty folder outside the current data root. On any failure the
        files and folders this call created are removed again.
        """
        with self._exclusive():
            self._validate_source()
            path = self._archive_path(backup_id)
            target = self._validate_target(target_root, allowed_parent)
            with self._temporary_file("restore-source") as extracted:
                try:
                    manifest = extract_and_verify(
                        path,
                        backup_id,
                        extracted,
                        max_database_bytes=self._max_database_bytes,
                    )
                except OSError:
                    raise BackupServiceError("The backup could not be read") from None
                created_root = False
                try:
                    target.mkdir()
                    created_root = True
                except FileExistsError:
                    pass
                except OSError:
                    raise RestoreTargetInvalid("The restore folder cannot be created") from None
                target_paths = StoragePaths.from_root(target)
                try:
                    summary = self._populate(target_paths, extracted, manifest)
                except BaseException:
                    self._remove_restored(target_paths, remove_root=created_root)
                    raise
            return RestoreResult(backup_id, target, summary)

    def _populate(
        self, target_paths: StoragePaths, extracted: Path, manifest: BackupManifest
    ) -> DatabaseSummary:
        try:
            self._checks.initialize(target_paths)
            with extracted.open("rb") as source, target_paths.database_file.open("xb") as output:
                while chunk := source.read(1_048_576):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            sha256, size = file_sha256(target_paths.database_file)
            if sha256 != manifest.database_sha256 or size != manifest.database_bytes:
                raise BackupServiceError("The restored copy did not match the backup")
            summary = check_sqlite_file(target_paths.database_file, immutable=False)
        except BackupServiceError:
            raise
        except BackupArchiveError:
            raise BackupServiceError("The restored copy did not pass verification") from None
        except Exception:  # noqa: BLE001 - restore failures never expose paths.
            raise BackupServiceError("The restored copy could not be written") from None
        if summary != manifest.summary:
            raise BackupServiceError("The restored copy did not match the backup")
        return summary

    def _remove_restored(self, target_paths: StoragePaths, *, remove_root: bool) -> None:
        """Remove exactly the paths a failed restore could have created."""
        database = target_paths.database_file
        for suffix in ("", *_SIDECAR_SUFFIXES):
            Path(f"{database}{suffix}").unlink(missing_ok=True)
        directories = [path for path in target_paths.directories if path != target_paths.root]
        if remove_root:
            directories.append(target_paths.root)
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                continue
