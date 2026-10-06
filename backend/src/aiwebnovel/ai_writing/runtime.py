"""An OS-owned lock protects restart recovery from another live instance."""

import sys
from pathlib import Path
from typing import BinaryIO

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class WorkflowRuntimeLock:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._stream: BinaryIO | None = None

    def acquire(self) -> bool:
        path = self._directory / "ai-workflow.lock"
        if self._directory.is_symlink() or path.is_symlink():
            return False
        stream = path.open("a+b")
        try:
            if path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            return False
        self._stream = stream
        return True

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
