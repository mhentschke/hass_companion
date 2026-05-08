"""Single-instance enforcement via fcntl.flock.

Uses a kernel-level file lock that is automatically released when the process
dies by any means (SIGTERM, SIGKILL, OOM, crash). No stale lock cleanup needed.

Works on Linux and macOS (both POSIX). Not supported on Windows.
"""

import fcntl
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Default lock file location — uses XDG runtime dir if available (auto-cleaned on logout),
# falls back to /tmp (persists across sessions but flock handles staleness).
_DEFAULT_LOCK_DIR = os.environ.get("XDG_RUNTIME_DIR", "/tmp")


class InstanceAlreadyRunning(Exception):
    """Raised when another instance of hass-companion is already running."""

    def __init__(self, pid: int | None = None):
        self.pid = pid
        msg = "Another instance of hass-companion is already running"
        if pid:
            msg += f" (PID: {pid})"
        super().__init__(msg)


class SingleInstanceLock:
    """Kernel-level file lock ensuring only one instance runs at a time.

    The lock is held for the lifetime of the process. On process death (any cause),
    the kernel closes the file descriptor and releases the lock automatically.

    Usage:
        lock = SingleInstanceLock(device_id="my_device")
        lock.acquire()  # raises InstanceAlreadyRunning if another instance holds it
        # ... run app ...
        lock.release()  # optional — released automatically on exit
    """

    def __init__(self, device_id: str, lock_dir: str | None = None):
        """Initialize the lock.

        Args:
            device_id: Used to create a unique lock file per config.
                       Allows running multiple instances with different configs.
            lock_dir: Directory for the lock file. Defaults to XDG_RUNTIME_DIR or /tmp.
        """
        lock_dir = lock_dir or _DEFAULT_LOCK_DIR
        safe_id = device_id.replace("/", "_").replace(" ", "_")
        self._lock_path = Path(lock_dir) / f"hass-companion-{safe_id}.lock"
        self._lock_fd: int | None = None

    @property
    def lock_path(self) -> Path:
        """Path to the lock file."""
        return self._lock_path

    def acquire(self) -> None:
        """Acquire the instance lock.

        Raises:
            InstanceAlreadyRunning: If another instance holds the lock.
        """
        # Open (or create) the lock file
        self._lock_fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o644)

        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            # Lock is held by another process — read its PID for diagnostics
            existing_pid = self._read_pid()
            os.close(self._lock_fd)
            self._lock_fd = None
            raise InstanceAlreadyRunning(pid=existing_pid)

        # Write our PID for debugging (cat the lock file to see who holds it)
        os.ftruncate(self._lock_fd, 0)
        os.lseek(self._lock_fd, 0, os.SEEK_SET)
        os.write(self._lock_fd, f"{os.getpid()}\n".encode())
        # Don't close the fd — closing releases the lock!
        logger.debug("Instance lock acquired: %s (PID: %d)", self._lock_path, os.getpid())

    def release(self) -> None:
        """Explicitly release the lock. Optional — released on process exit."""
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
            logger.debug("Instance lock released: %s", self._lock_path)

    def _read_pid(self) -> int | None:
        """Try to read the PID from an existing lock file."""
        try:
            with open(self._lock_path) as f:
                content = f.read().strip()
                return int(content) if content else None
        except (OSError, ValueError):
            return None
