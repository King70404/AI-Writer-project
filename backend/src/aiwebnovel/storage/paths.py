"""Immutable local storage paths derived from one validated root."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from aiwebnovel.core.config import Settings, normalize_data_root


class StoragePathError(ValueError):
    """Raised when managed paths cannot be kept inside their configured root."""


def _is_within_root(root: Path, candidate: Path) -> bool:
    try:
        common = os.path.commonpath((os.fspath(root), os.fspath(candidate)))
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(os.fspath(root))


@dataclass(frozen=True, slots=True)
class StoragePaths:
    """All authoritative paths for one application instance."""

    root: Path
    data: Path = field(init=False)
    database_file: Path = field(init=False)
    assets: Path = field(init=False)
    runtime: Path = field(init=False)
    runtime_app: Path = field(init=False)
    runtime_temp: Path = field(init=False)
    runtime_locks: Path = field(init=False)
    models: Path = field(init=False)
    backups: Path = field(init=False)
    exports: Path = field(init=False)
    logs: Path = field(init=False)
    config: Path = field(init=False)

    def __post_init__(self) -> None:
        """Derive every managed path from root even for direct construction."""
        normalized_root = normalize_data_root(self.root)
        data = normalized_root / "data"
        runtime = normalized_root / "runtime"
        derived = {
            "root": normalized_root,
            "data": data,
            "database_file": data / "aiwebnovel.sqlite3",
            "assets": normalized_root / "assets",
            "runtime": runtime,
            "runtime_app": runtime / "app",
            "runtime_temp": runtime / "temp",
            "runtime_locks": runtime / "locks",
            "models": normalized_root / "models",
            "backups": normalized_root / "backups",
            "exports": normalized_root / "exports",
            "logs": normalized_root / "logs",
            "config": normalized_root / "config",
        }
        for name, value in derived.items():
            object.__setattr__(self, name, value)
        self._validate_boundaries()

    @classmethod
    def from_root(cls, root: str | os.PathLike[str]) -> StoragePaths:
        """Derive the fixed layout without creating or inspecting any path."""
        return cls(root=Path(root))

    @classmethod
    def from_settings(cls, settings: Settings) -> StoragePaths:
        """Derive one application's layout from validated settings."""
        return cls.from_root(settings.data_root)

    @property
    def directories(self) -> tuple[Path, ...]:
        """Return the fixed initialization order, including the root."""
        return (
            self.root,
            self.data,
            self.assets,
            self.runtime,
            self.runtime_app,
            self.runtime_temp,
            self.runtime_locks,
            self.models,
            self.backups,
            self.exports,
            self.logs,
            self.config,
        )

    def _validate_boundaries(self) -> None:
        for candidate in (*self.directories, self.database_file):
            if candidate != self.root and not _is_within_root(self.root, candidate):
                raise StoragePathError("A managed storage path escaped the data root")
