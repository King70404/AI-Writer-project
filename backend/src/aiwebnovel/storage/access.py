"""Current-process read, write, flush, reread, and delete probes."""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from aiwebnovel.storage.paths import StoragePaths

ProbeTokenFactory = Callable[[], str]


class StorageAccessError(RuntimeError):
    """Raised with a path-free message when an access invariant fails."""


@dataclass(frozen=True, slots=True)
class StorageAccessResult:
    """Verified capabilities without local path or probe-name content."""

    root_readable: bool
    data_read_write_delete: bool
    runtime_temp_read_write_delete: bool


def _random_probe_token() -> str:
    return secrets.token_hex(18)


def _probe_directory(directory: Path, token_factory: ProbeTokenFactory) -> None:
    token = token_factory()
    if not token or not token.isascii() or not token.isalnum():
        raise StorageAccessError("Storage probe token generation failed")

    probe_path = directory / f".aiwebnovel-access-{token}.tmp"
    payload = f"AIWebNovel storage access probe {token}\n".encode()
    created = False
    operation_error: BaseException | None = None

    try:
        with probe_path.open("xb") as probe:
            created = True
            probe.write(payload)
            probe.flush()
            os.fsync(probe.fileno())
        if probe_path.read_bytes() != payload:
            raise StorageAccessError("Storage probe content verification failed")
        probe_path.unlink()
        created = False
    except Exception as exc:  # noqa: BLE001 - filesystem failures become one safe error.
        operation_error = exc
    finally:
        cleanup_error: OSError | None = None
        if created:
            try:
                probe_path.unlink(missing_ok=True)
            except OSError as exc:
                cleanup_error = exc
        if operation_error is not None or cleanup_error is not None:
            cause = cleanup_error or operation_error
            raise StorageAccessError(
                "Storage read, write, and delete verification failed"
            ) from cause


def verify_storage_access(
    paths: StoragePaths,
    *,
    probe_token_factory: ProbeTokenFactory | None = None,
) -> StorageAccessResult:
    """Verify root readability plus destructive capability in two safe directories."""
    token_factory = probe_token_factory or _random_probe_token
    try:
        with os.scandir(paths.root) as entries:
            next(entries, None)
    except OSError as exc:
        raise StorageAccessError("Storage root read verification failed") from exc

    _probe_directory(paths.data, token_factory)
    _probe_directory(paths.runtime_temp, token_factory)
    return StorageAccessResult(
        root_readable=True,
        data_read_write_delete=True,
        runtime_temp_read_write_delete=True,
    )


def check_storage_access(
    paths: StoragePaths,
    *,
    probe_token_factory: ProbeTokenFactory | None = None,
) -> StorageAccessResult:
    """Compatibility name for the explicit current-process access probe."""
    return verify_storage_access(paths, probe_token_factory=probe_token_factory)
