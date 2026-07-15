"""Test-only application factories with mandatory storage isolation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI

from aiwebnovel.core.config import Settings
from aiwebnovel.main import create_app


class TestStorageIsolationError(ValueError):
    """Raised before a test application can use an implicit data root."""

    __test__ = False


def create_test_settings(
    *,
    data_root: Path | None,
    **overrides: Any,
) -> Settings:
    """Build test settings only when an explicit absolute data root is supplied."""
    if data_root is None or not data_root.is_absolute():
        raise TestStorageIsolationError(
            "test applications require an explicit absolute temporary data root"
        )
    values: dict[str, Any] = {
        "environment": "test",
        "data_root": data_root,
    }
    values.update(overrides)
    return Settings(**values)


def create_test_app(
    *,
    data_root: Path | None,
    **overrides: Any,
) -> FastAPI:
    """Create an isolated test application without consulting the user data default."""
    return create_app(create_test_settings(data_root=data_root, **overrides))
