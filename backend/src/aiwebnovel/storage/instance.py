"""A stable, path-free identifier for one data root, used to isolate browser drafts.

The identifier has no authentication purpose and reveals no path. It survives a
normal restart of the same data root. A restored copy (a new root that receives
only the database) or a root moved/copied elsewhere gets a new identifier, because
the stored fingerprint of the root location no longer matches.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from threading import Lock
from uuid import uuid4

from aiwebnovel.core.config import normalize_data_root

_FILENAME = "storage-instance.json"
_IDENTIFIER = re.compile(r"[0-9a-f]{32}\Z")
_LOCK = Lock()


class StorageInstanceUnavailable(RuntimeError):
    """The identifier could not be read or created; no path is revealed."""


def _fingerprint(root: Path) -> str:
    return hashlib.sha256(os.path.normcase(os.fspath(root)).encode("utf-8")).hexdigest()


class StorageInstanceService:
    def __init__(self, data_root: Path) -> None:
        self._root = normalize_data_root(data_root)
        self._directory = self._root / "config"
        self._target = self._directory / _FILENAME

    def _check_links(self) -> None:
        for path in (self._root, self._directory, self._target):
            if path.is_symlink() or path.is_junction():
                raise StorageInstanceUnavailable

    def _read(self) -> str | None:
        if not self._target.is_file():
            return None
        try:
            data = json.loads(self._target.read_bytes())
        except (OSError, ValueError):
            return None
        if (
            type(data) is not dict
            or data.get("version") != 1
            or type(data.get("id")) is not str
            or not _IDENTIFIER.fullmatch(data["id"])
            or data.get("root") != _fingerprint(self._root)
        ):
            return None
        return str(data["id"])

    def get(self) -> str:
        with _LOCK:
            try:
                self._check_links()
                existing = self._read()
                if existing is not None:
                    return existing
                identifier = uuid4().hex
                payload = json.dumps(
                    {"version": 1, "id": identifier, "root": _fingerprint(self._root)}
                ).encode("ascii")
                self._directory.mkdir(parents=True, exist_ok=True)
                self._check_links()
                temporary: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(dir=self._directory, delete=False) as stream:
                        temporary = Path(stream.name)
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, self._target)
                    temporary = None
                finally:
                    if temporary is not None and temporary.exists():
                        temporary.unlink()
                return identifier
            except OSError:
                raise StorageInstanceUnavailable from None
