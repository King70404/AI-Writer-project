"""Backend-test isolation that prevents access to the real user data root."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from aiwebnovel.core.config import get_settings


@pytest.fixture(autouse=True)
def isolated_backend_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Path]:
    """Give every backend test a unique explicit data root and remove it afterward."""
    data_root = tmp_path / "aiwebnovel-test-data-root"
    monkeypatch.setenv("AIWEBNOVEL_DATA_ROOT", os.fspath(data_root))
    monkeypatch.delenv("AIWEBNOVEL_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        yield data_root
    finally:
        get_settings.cache_clear()
        if data_root.exists():
            assert data_root.is_relative_to(tmp_path)
            assert not data_root.is_symlink()
            shutil.rmtree(data_root)
