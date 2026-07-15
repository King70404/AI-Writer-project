"""On-demand storage initialization and reparse-point safety tests."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aiwebnovel.storage.initializer import (
    StorageInitializationError,
    initialize_storage,
    is_reparse_point,
    validate_storage_layout,
)
from aiwebnovel.storage.paths import StoragePaths

pytestmark = pytest.mark.unit


def test_initializer_creates_the_complete_directory_layout(tmp_path: Path) -> None:
    paths = StoragePaths.from_root(tmp_path / "storage")

    result = initialize_storage(paths)

    assert result.created_directories == 12
    assert result.total_directories == 12
    assert all(path.is_dir() for path in paths.directories)
    assert not paths.database_file.exists()
    assert not any(path.is_file() for path in paths.root.rglob("*"))


def test_initializer_is_idempotent_and_preserves_existing_content(tmp_path: Path) -> None:
    paths = StoragePaths.from_root(tmp_path / "storage")
    first = initialize_storage(paths)
    sentinel = paths.assets / "existing-sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    second = initialize_storage(paths)

    assert first.created_directories == 12
    assert second.created_directories == 0
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_root_file_is_rejected_without_being_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    root.write_text("do-not-overwrite", encoding="utf-8")

    with pytest.raises(StorageInitializationError) as failure:
        initialize_storage(StoragePaths.from_root(root))

    assert root.read_text(encoding="utf-8") == "do-not-overwrite"
    assert str(root) not in str(failure.value)


def test_required_subdirectory_file_is_rejected_without_deletion(tmp_path: Path) -> None:
    paths = StoragePaths.from_root(tmp_path / "storage")
    paths.root.mkdir()
    paths.data.write_text("not-a-directory", encoding="utf-8")

    with pytest.raises(StorageInitializationError):
        initialize_storage(paths)

    assert paths.data.read_text(encoding="utf-8") == "not-a-directory"


def test_mid_initialization_failure_is_not_reported_as_success(tmp_path: Path) -> None:
    paths = StoragePaths.from_root(tmp_path / "storage")

    def controlled_detector(path: Path) -> bool:
        if path == paths.runtime and path.exists():
            raise OSError("controlled attribute failure")
        return False

    with pytest.raises(StorageInitializationError):
        initialize_storage(paths, reparse_detector=controlled_detector)

    assert paths.root.is_dir()
    assert paths.data.is_dir()
    assert not paths.runtime_app.exists()
    assert not paths.database_file.exists()


def test_root_reparse_point_is_rejected_before_child_writes(tmp_path: Path) -> None:
    paths = StoragePaths.from_root(tmp_path / "storage")

    with pytest.raises(StorageInitializationError):
        initialize_storage(
            paths,
            reparse_detector=lambda path: path == paths.root,
        )

    assert paths.root.is_dir()
    assert not paths.data.exists()


def test_child_reparse_point_is_rejected_without_following_or_deleting(
    tmp_path: Path,
) -> None:
    paths = StoragePaths.from_root(tmp_path / "storage")
    initialize_storage(paths)
    sentinel = paths.assets / "preserved.txt"
    sentinel.write_text("preserved", encoding="utf-8")

    with pytest.raises(StorageInitializationError) as failure:
        validate_storage_layout(
            paths,
            reparse_detector=lambda path: path == paths.assets,
        )

    assert sentinel.read_text(encoding="utf-8") == "preserved"
    assert str(paths.assets) not in str(failure.value)


def test_ordinary_directory_is_not_a_reparse_point(tmp_path: Path) -> None:
    directory = tmp_path / "ordinary"
    directory.mkdir()

    assert is_reparse_point(directory) is False


@pytest.mark.skipif(os.name != "nt", reason="Windows file attributes are Windows-specific")
def test_windows_reparse_attribute_is_detected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_stat = SimpleNamespace(
        st_mode=stat.S_IFDIR,
        st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
    )
    monkeypatch.setattr(Path, "lstat", lambda _path: fake_stat)

    assert is_reparse_point(tmp_path / "controlled") is True


def test_non_windows_branch_does_not_claim_windows_attribute_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aiwebnovel.storage import initializer

    fake_stat = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
    monkeypatch.setattr(Path, "lstat", lambda _path: fake_stat)
    monkeypatch.setattr(initializer.os, "name", "posix")

    assert initializer.is_reparse_point(tmp_path / "controlled") is False


def test_importing_storage_modules_has_no_filesystem_side_effect(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "import-only-root"
    environment = os.environ.copy()
    environment["AIWEBNOVEL_DATA_ROOT"] = str(data_root)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    repository_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import aiwebnovel.storage.paths; "
                "import aiwebnovel.storage.initializer; "
                "import aiwebnovel.storage.access; "
                "import aiwebnovel.storage.health"
            ),
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not data_root.exists()
