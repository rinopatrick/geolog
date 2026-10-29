"""Cross-process file lock for the JSON state files.

The server can run several uvicorn workers. A `threading.Lock` only protects
threads inside one worker, so read-modify-write on metrics, jobs, audit chain,
locks and snapshots needs an OS-level lock as well.

Works on Windows (`msvcrt`) and POSIX (`fcntl`). The lock is advisory: every
writer in this codebase must use it.

The lock file name is a hash of the requested logical path and always lives in
GEOLOG_ARTIFACT_DIR. Callers never control a filesystem path here, which keeps
the lock primitive free of path traversal.
"""

from __future__ import annotations

import hashlib
import os
import time
from contextlib import contextmanager

if os.name == "nt":  # pragma: no cover - exercised on Windows
    import msvcrt
else:  # pragma: no cover - exercised on Linux CI
    import fcntl


def _lock_root() -> str:
    return os.path.abspath(
        os.getenv("GEOLOG_ARTIFACT_DIR")
        or os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")
    )


@contextmanager
def interprocess_lock(path: str, timeout: float = 10.0):
    """Hold an exclusive lock for the logical `path` for the duration of the block."""
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()
    root = _lock_root()
    os.makedirs(root, exist_ok=True)
    lock_path = os.path.join(root, f"state-{digest}.lock")

    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"could not acquire file lock for {path}")
                time.sleep(0.02)
        yield
    finally:
        try:
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
