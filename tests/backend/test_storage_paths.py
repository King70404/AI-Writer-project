"""Pure StoragePaths derivation, containment, and immutability tests."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from aiwebnovel.storage.paths import StoragePaths

pytestmark = pytest.mark.unit


def test_storage_paths_are_derived_from_one_normalized_root(tmp_path: Path) -> None:
    root = tmp_path / "data root with spaces" / ".." / "managed root"

    paths = StoragePaths.from_root(root)

    assert paths.root == tmp_path / "managed root"
    assert paths.data == paths.root / "data"
    assert paths.database_file == paths.data / "aiwebnovel.sqlite3"
    assert paths.assets == paths.root / "assets"
    assert paths.runtime == paths.root / "runtime"
    assert paths.runtime_app == paths.runtime / "app"
    assert paths.runtime_temp == paths.runtime / "temp"
    assert paths.runtime_locks == paths.runtime / "locks"
    assert paths.models == paths.root / "models"
    assert paths.backups == paths.root / "backups"
    assert paths.exports == paths.root / "exports"
    assert paths.logs == paths.root / "logs"
    assert paths.config == paths.root / "config"
    assert len(paths.directories) == 12
    assert not paths.root.exists()


def test_every_managed_path_stays_inside_the_root(tmp_path: Path) -> None:
    paths = StoragePaths.from_root(tmp_path / "root")

    for candidate in (*paths.directories, paths.database_file):
        assert candidate == paths.root or candidate.is_relative_to(paths.root)


def test_storage_paths_are_frozen(tmp_path: Path) -> None:
    paths = StoragePaths.from_root(tmp_path / "root")

    with pytest.raises(FrozenInstanceError):
        paths.root = tmp_path / "other"  # type: ignore[misc]


def test_path_derivation_does_not_create_directories(tmp_path: Path) -> None:
    root = tmp_path / "not-created"

    StoragePaths.from_root(root)

    assert not root.exists()
