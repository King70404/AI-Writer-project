"""Storage health composition and path-free failure tests."""

from pathlib import Path

import pytest

from aiwebnovel.storage.health import check_storage_health
from aiwebnovel.storage.initializer import StorageInitializationError, initialize_storage
from aiwebnovel.storage.paths import StoragePaths

pytestmark = pytest.mark.unit


def test_storage_health_runs_real_layout_and_access_checks(tmp_path: Path) -> None:
    paths = StoragePaths.from_root(tmp_path / "storage")
    initialize_storage(paths)

    result = check_storage_health(paths)

    assert result.status == "ok"
    assert result.access.root_readable is True
    assert result.access.data_read_write_delete is True
    assert result.access.runtime_temp_read_write_delete is True
    assert not list(paths.root.rglob(".aiwebnovel-access-*.tmp"))


def test_storage_health_rejects_an_incomplete_layout_without_path_leakage(
    tmp_path: Path,
) -> None:
    paths = StoragePaths.from_root(tmp_path / "storage")
    paths.root.mkdir()

    with pytest.raises(StorageInitializationError) as failure:
        check_storage_health(paths)

    assert str(paths.root) not in str(failure.value)
