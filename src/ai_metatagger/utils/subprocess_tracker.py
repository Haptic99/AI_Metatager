"""Lightweight subprocess tracker for cancellable external process execution.

Provides a registry that tracks running subprocesses so they can be
terminated when an analysis is cancelled by the user.
"""
import os
import subprocess
import threading
from typing import List, Optional


class SubprocessTracker:
    """Tracks running subprocesses and allows bulk termination.

    Usage:
        tracker = SubprocessTracker()
        result = tracker.run(["ffmpeg", ...], stdout=subprocess.PIPE)
        # Later, to cancel all running processes:
        tracker.cancel()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: List[subprocess.Popen] = []
        self._cancelled = False

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self, cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
        """Run a subprocess while tracking it for cancellation.

        Args:
            cmd: Command and arguments to execute.
            **kwargs: Additional arguments passed to subprocess.Popen.

        Returns:
            subprocess.CompletedProcess with returncode, stdout, stderr.
        """
        if self._cancelled:
            return subprocess.CompletedProcess(cmd, returncode=1, stdout=b'', stderr=b'cancelled')

        if kwargs.pop('capture_output', False):
            kwargs['stdout'] = subprocess.PIPE
            kwargs['stderr'] = subprocess.PIPE
            
        check = kwargs.pop('check', False)

        if os.name == 'nt':
            kwargs.setdefault('creationflags', 0x08000000)  # CREATE_NO_WINDOW

        proc = subprocess.Popen(cmd, **kwargs)
        with self._lock:
            self._processes.append(proc)
        try:
            stdout, stderr = proc.communicate()
            if check and proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd, output=stdout, stderr=stderr)
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        finally:
            with self._lock:
                try:
                    self._processes.remove(proc)
                except ValueError:
                    pass

    def cancel(self) -> None:
        """Signal cancellation and terminate all tracked subprocesses."""
        self._cancelled = True
        with self._lock:
            for proc in self._processes:
                try:
                    proc.terminate()
                except OSError:
                    pass

    def reset(self) -> None:
        """Reset cancellation state for reuse."""
        self._cancelled = False
        with self._lock:
            self._processes.clear()


# Module-level default tracker for use when no explicit tracker is provided.
_default_tracker: Optional[SubprocessTracker] = None


def get_active_tracker() -> Optional[SubprocessTracker]:
    """Return the currently active tracker, if any."""
    return _default_tracker


def set_active_tracker(tracker: Optional[SubprocessTracker]) -> None:
    """Set the module-level active tracker."""
    global _default_tracker
    _default_tracker = tracker


def tracked_run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command using the active tracker, or plain subprocess.run as fallback.

    This is a drop-in replacement for subprocess.run() that automatically
    uses the active SubprocessTracker if one has been set.
    """
    tracker = _default_tracker
    if tracker is not None:
        return tracker.run(cmd, **kwargs)
    # Fallback: no tracker active, run normally
    if os.name == 'nt':
        kwargs.setdefault('creationflags', 0x08000000)
    return subprocess.run(cmd, **kwargs)
