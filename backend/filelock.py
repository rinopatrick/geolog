"""Cross-process file lock for the JSON state files.

The server can run several uvicorn workers. A `threading.Lock` only protects
threads inside one worker, so read-modify-write on metrics, jobs, audit chain,
locks and snapshots needs an OS-level lock as well.

Works on Windows (`msvcrt`) and POSIX (`fcntl`). The lock is advisory: every
writer in this codebase must use it.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

if os.name == "nt":  # pragma: no cover - exercised on Windows
    import msvcrt
else:  # pragma: no cover - exercised on Linux CI
    import fcntl

@contextmanager
def interprocess_lock(path: str, timeout: float = 10.0):
    """Hold an exclusive lock on `path+'.lock'` for the duration of the block."""
    lock_path = path if path.endswith(".lock") else path + ".lock"
    parent = os.path.dirname(os.path.abspath(lock_path))
    if parent:
        os.makedirs(parent, exist_ok=True)  # codeql[py/path-injection]

    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)  # codeql[py/path-injection]
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
                    raise TimeoutError(f"could not acquire file lock {lock_path}")
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
