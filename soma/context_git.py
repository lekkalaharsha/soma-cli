"""Git commit and file scanning helper functions for SOMA context generation."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from soma.filters import is_watched, should_ignore

MAX_FILES = 8
FILE_WALK_BUDGET_S = 0.3


def _fetch_commit_stats(root: Path, n: int) -> list[tuple[int, int]]:
    """(insertions, deletions) for the last n commits. Empty list on any error."""
    try:
        from git import Repo  # noqa: PLC0415
        from git.exc import GitCommandError, GitCommandNotFound, InvalidGitRepositoryError  # noqa: PLC0415

        repo = Repo(root)
        out = repo.git.log(f"--max-count={n}", "--pretty=format:COMMIT", "--shortstat")
    except (GitCommandError, InvalidGitRepositoryError, GitCommandNotFound, OSError):
        return []
    stats: list[tuple[int, int]] = []
    ins, dels = 0, 0
    in_commit = False
    for line in out.splitlines():
        stripped = line.strip()
        if stripped == "COMMIT":
            if in_commit:
                stats.append((ins, dels))
            ins, dels, in_commit = 0, 0, True
        elif in_commit and stripped:
            m_ins = re.search(r"(\d+) insertion", stripped)
            m_del = re.search(r"(\d+) deletion", stripped)
            ins += int(m_ins.group(1)) if m_ins else 0
            dels += int(m_del.group(1)) if m_del else 0
    if in_commit:
        stats.append((ins, dels))
    return stats


def _files_in_motion(root: Path, candidates: list[str]) -> list[tuple[str, datetime]]:
    """Attach mtimes to git-changed paths, newest first (deleted files drop out)."""
    out: list[tuple[str, datetime]] = []
    for rel in candidates:
        try:
            ts = (root / rel).stat().st_mtime
        except OSError:
            continue
        out.append((rel, datetime.fromtimestamp(ts, tz=timezone.utc)))
    out.sort(key=lambda item: item[1], reverse=True)
    return out[:MAX_FILES]


def _recent_files_by_mtime(
    root: Path,
    now: datetime | None = None,
    dormant_days: int = 30,
) -> list[tuple[str, datetime]]:
    """Fallback for non-git/quiet repos: newest watched files by mtime.

    Files older than dormant_days are omitted — showing 86d-old files as
    "in motion" is misleading for dormant repos.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=dormant_days)).timestamp()
    deadline = time.monotonic() + FILE_WALK_BUDGET_S
    found: list[tuple[str, float]] = []
    _walk_files(str(root), root, deadline, found)
    found.sort(key=lambda item: item[1], reverse=True)
    return [
        (rel, datetime.fromtimestamp(ts, tz=timezone.utc))
        for rel, ts in found[:MAX_FILES]
        if ts >= cutoff
    ]


def _walk_files(
    directory: str, root: Path, deadline: float, found: list[tuple[str, float]]
) -> None:
    if time.monotonic() > deadline:
        return
    try:
        with os.scandir(directory) as it:
            for entry in it:
                name = entry.name
                if name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not should_ignore(name):
                            _walk_files(entry.path, root, deadline, found)
                    elif is_watched(name) and not should_ignore(name):
                        ts = entry.stat(follow_symlinks=False).st_mtime
                        rel = Path(entry.path).relative_to(root).as_posix()
                        found.append((rel, ts))
                except (OSError, ValueError):
                    continue
    except OSError:
        pass
