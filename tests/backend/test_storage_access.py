"""Storage access probe success, failure, cleanup, and uniqueness tests."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from aiwebnovel.storage.access import StorageAccessError, verify_storage_access
from aiwebnovel.storage.initializer import initialize_storage
from aiwebnovel.storage.paths import StoragePaths

pytestmark = pytest.mark.unit


def _initialized_paths(tmp_path: Path) -> StoragePaths:
    paths = StoragePaths.from_root(tmp_path / "storage")
    initialize_storage(paths)
    return paths


def _probe_files(paths: StoragePaths) -> list[Path]:
    return [
        *paths.data.glob(".aiwebnovel-access-*.tmp"),
        *paths.runtime_temp.glob(".aiwebnovel-access-*.tmp"),
    ]


def test_real_probe_reads_writes_flushes_rereads_and_deletes(tmp_path: Path) -> None:
    paths = _initialized_paths(tmp_path)

    result = verify_storage_access(paths)

    assert result.root_readable is True
    assert result.data_read_write_delete is True
    assert result.runtime_temp_read_write_delete is True
    assert _probe_files(paths) == []


def test_exclusive_probe_never_overwrites_an_existing_file(tmp_path: Path) -> None:
    paths = _initialized_paths(tmp_path)
    existing = paths.data / ".aiwebnovel-access-duplicate.tmp"
    existing.write_text("preserve", encoding="utf-8")

    with pytest.raises(StorageAccessError):
        verify_storage_access(paths, probe_token_factory=lambda: "duplicate")

    assert existing.read_text(encoding="utf-8") == "preserve"


def test_write_failure_is_safe_and_leaves_no_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path)
    original_open = Path.open

    def denied_open(path: Path, *args: Any, **kwargs: Any):
        if path.name.startswith(".aiwebnovel-access-"):
            raise PermissionError("controlled write failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_open)

    with pytest.raises(StorageAccessError) as failure:
        verify_storage_access(paths)

    assert _probe_files(paths) == []
    assert str(paths.root) not in str(failure.value)


def test_read_failure_attempts_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path)
    original_read = Path.read_bytes

    def denied_read(path: Path) -> bytes:
        if path.name.startswith(".aiwebnovel-access-"):
            raise OSError("controlled read failure")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", denied_read)

    with pytest.raises(StorageAccessError):
        verify_storage_access(paths)

    assert _probe_files(paths) == []


def test_content_mismatch_fails_and_cleans_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path)
    monkeypatch.setattr(Path, "read_bytes", lambda _path: b"controlled mismatch")

    with pytest.raises(StorageAccessError):
        verify_storage_access(paths)

    assert _probe_files(paths) == []


def test_delete_failure_is_reported_and_second_cleanup_is_attempted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path)
    original_unlink = Path.unlink
    delete_attempts = 0

    def denied_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        nonlocal delete_attempts
        if path.name.startswith(".aiwebnovel-access-"):
            delete_attempts += 1
            raise PermissionError("controlled delete failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", denied_unlink)

    with pytest.raises(StorageAccessError):
        verify_storage_access(paths)

    remaining = _probe_files(paths)
    assert delete_attempts >= 2
    assert len(remaining) == 1
    monkeypatch.setattr(Path, "unlink", original_unlink)
    remaining[0].unlink()


def test_root_read_failure_is_reported_without_a_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path)

    def denied_scan(_path: Path):
        raise PermissionError("controlled root read failure")

    monkeypatch.setattr(os, "scandir", denied_scan)

    with pytest.raises(StorageAccessError) as failure:
        verify_storage_access(paths)

    assert str(paths.root) not in str(failure.value)
    assert _probe_files(paths) == []


def test_concurrent_probes_use_distinct_unpredictable_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths = _initialized_paths(tmp_path)
    original_open = Path.open
    observed_names: set[str] = set()
    lock = threading.Lock()

    def recording_open(path: Path, *args: Any, **kwargs: Any):
        if args and args[0] == "xb":
            with lock:
                assert path.name not in observed_names
                observed_names.add(path.name)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording_open)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: verify_storage_access(paths), range(2)))

    assert all(result.root_readable for result in results)
    assert len(observed_names) == 4
    assert _probe_files(paths) == []
