"""Directory mtime scanning heuristics for watched files."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from soma.filters import is_watched, should_ignore

MTIME_BUDGET_S = 0.6  # mtime walk self-truncates so huge repos degrade, not skip


class _ScanState:
    __slots__ = ("deadline", "latest", "truncated")

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self.latest = 0.0
        self.truncated = False


def _scan_mtimes(directory: str, state: _ScanState) -> None:
    # scandir's stat info comes free with the directory listing on Windows —
    # avoiding one stat syscall per file is what keeps big repos in budget.
    if time.monotonic() > state.deadline:
        state.truncated = True
        return
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if state.truncated:
                    return
                name = entry.name
                if name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not should_ignore(name):
                            _scan_mtimes(entry.path, state)
                    elif is_watched(name) and not should_ignore(name):
                        ts = entry.stat(follow_symlinks=False).st_mtime
                        if ts > state.latest:
                            state.latest = ts
                except OSError:
                    continue
    except OSError:  # permission denied, vanished dir
        pass


def _latest_watched_mtime(root: Path) -> tuple[datetime | None, bool]:
    """(newest watched-file mtime, walk_truncated) under root.

    The walk gets a hard wall-clock budget: on huge repos (vendored SDKs,
    100k-file clones) it returns the best partial answer instead of making
    the whole repo miss the per-repo timeout and get skipped entirely.
    """
    state = _ScanState(deadline=time.monotonic() + MTIME_BUDGET_S)
    _scan_mtimes(str(root), state)
    when = (
        datetime.fromtimestamp(state.latest, tz=timezone.utc)
        if state.latest > 0.0
        else None
    )
    return when, state.truncated
