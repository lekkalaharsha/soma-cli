"""Project status: branch, last activity, recent commits, files changed (7d).

Data sources: git history via gitpython, plus watched-file mtimes as the
fallback activity signal for repos with stale or missing git history.
last_active = max(latest commit, newest watched mtime); git wins ties.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from pathlib import Path

from git import InvalidGitRepositoryError, NoSuchPathError, Repo
from git.exc import GitCommandError
from pydantic import BaseModel, Field

from soma.filters import is_watched, should_ignore

REPO_TIMEOUT_S = 1.0
MTIME_BUDGET_S = 0.6  # mtime walk self-truncates so huge repos degrade, not skip
MAX_RECENT_COMMITS = 5
MAX_CHANGED_FILES = 15
CHANGED_WINDOW_DAYS = 7

_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


class CommitInfo(BaseModel):
    message: str
    when: datetime


class ProjectStatus(BaseModel):
    name: str
    root: str
    branch: str = "—"
    last_active: datetime | None = None
    commits_7d: int = 0
    recent_commits: list[CommitInfo] = Field(default_factory=list)
    files_changed_7d: list[str] = Field(default_factory=list)
    warning: str | None = None


def get_status(name: str, root: Path, since: datetime | None = None) -> ProjectStatus:
    """Gather status for one project. Never raises on git problems.

    When `since` is provided, the activity window uses that date instead
    of the hardcoded 7-day window (commits_7d / files_changed_7d still use
    those field names for model compatibility).
    """
    status = ProjectStatus(name=name, root=str(root))
    mtime, _ = _latest_watched_mtime(root)  # truncation is expected on large repos, not a warning
    git_time: datetime | None = None
    try:
        repo = Repo(root)
        status.branch = _branch_name(repo)
        status.recent_commits = _recent_commits(repo)
        if since is not None:
            status.commits_7d, status.files_changed_7d = _activity_since(repo, since)
        else:
            status.commits_7d, status.files_changed_7d = _activity_7d(repo)
        if status.recent_commits:
            git_time = status.recent_commits[0].when
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError):
        pass  # non-git or broken repo — mtimes still give us last_active
    if git_time is not None and (mtime is None or git_time >= mtime):
        status.last_active = git_time
    else:
        status.last_active = mtime
    return status


def get_status_safe(name: str, root: Path) -> ProjectStatus:
    """get_status with a hard per-repo timeout — skip with warning, never hang."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(get_status, name, root)
        try:
            return future.result(timeout=REPO_TIMEOUT_S)
        except FutureTimeoutError:
            return ProjectStatus(
                name=name,
                root=str(root),
                warning=f"skipped — scan exceeded {REPO_TIMEOUT_S:.0f}s",
            )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def collect_statuses(registry: dict[str, dict]) -> list[ProjectStatus]:
    """Status for every registered project, most recent activity first.

    One shared pool; the per-repo timeout counts from when that repo's
    scan actually starts (not from submit), so repos queued behind slow
    ones aren't unfairly skipped. A global deadline still guarantees the
    command can never hang.
    """
    pool = ThreadPoolExecutor(max_workers=8)
    started: dict[str, float] = {}

    def job(name: str, root: Path) -> ProjectStatus:
        started[name] = time.monotonic()
        return get_status(name, root)

    futures = [
        (name, entry, pool.submit(job, name, Path(entry["root"])))
        for name, entry in registry.items()
    ]
    deadline = time.monotonic() + REPO_TIMEOUT_S * max(8.0, float(len(futures)))
    statuses: list[ProjectStatus] = []
    try:
        for name, entry, future in futures:
            try:
                statuses.append(_await_result(future, name, started, deadline))
            except FutureTimeoutError:
                future.cancel()
                statuses.append(
                    ProjectStatus(
                        name=name,
                        root=str(entry["root"]),
                        warning=f"skipped — scan exceeded {REPO_TIMEOUT_S:.0f}s",
                    )
                )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    statuses.sort(key=lambda s: s.last_active or _EPOCH, reverse=True)
    return statuses


def _await_result(
    future: Future[ProjectStatus],
    name: str,
    started: dict[str, float],
    deadline: float,
) -> ProjectStatus:
    while True:
        try:
            return future.result(timeout=0.05)
        except FutureTimeoutError:
            now = time.monotonic()
            begun = started.get(name)
            if begun is not None and now - begun > REPO_TIMEOUT_S:
                raise
            if now > deadline:
                raise


def humanize_delta(when: datetime | None, now: datetime | None = None) -> str:
    """'just now' / '5m ago' / '2h ago' / '3d ago'; '—' for unknown."""
    if when is None:
        return "—"
    now = now or datetime.now(timezone.utc)
    seconds = max(0.0, (now - when).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def _branch_name(repo: Repo) -> str:
    try:
        return repo.active_branch.name
    except (TypeError, ValueError):  # detached HEAD
        return "—"


def _recent_commits(repo: Repo) -> list[CommitInfo]:
    # Plain `git log` instead of iter_commits: one subprocess instead of
    # persistent cat-file helpers — process spawns dominate cost on Windows.
    try:
        out = repo.git.log(
            f"--max-count={MAX_RECENT_COMMITS}", "--pretty=format:%ct%x09%s"
        )
    except GitCommandError:  # unborn HEAD — zero commits
        return []
    commits: list[CommitInfo] = []
    for line in out.splitlines():
        ts, _, message = line.partition("\t")
        if not ts.isdigit():
            continue
        commits.append(
            CommitInfo(
                message=message,
                when=datetime.fromtimestamp(int(ts), tz=timezone.utc),
            )
        )
    return commits


def _activity_7d(repo: Repo) -> tuple[int, list[str]]:
    """(commit count, changed watched files) in the last 7 days, one git call."""
    try:
        out = repo.git.log(
            f"--since={CHANGED_WINDOW_DAYS}.days.ago",
            "--name-only",
            "--pretty=format:@%H",
        )
    except GitCommandError:  # unborn HEAD — zero commits
        return 0, []
    commits = 0
    files: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("@") and len(line) == 41:
            commits += 1
            continue
        if should_ignore(line) or not is_watched(line):
            continue
        if line not in files and len(files) < MAX_CHANGED_FILES:
            files.append(line)
    return commits, files


def _activity_since(repo: Repo, since: datetime) -> tuple[int, list[str]]:
    """(commit count, changed watched files) since a given datetime, one git call."""
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        out = repo.git.log(
            f"--after={since_iso}",
            "--name-only",
            "--pretty=format:@%H",
        )
    except GitCommandError:
        return 0, []
    commits = 0
    files: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("@") and len(line) == 41:
            commits += 1
            continue
        if should_ignore(line) or not is_watched(line):
            continue
        if line not in files and len(files) < MAX_CHANGED_FILES:
            files.append(line)
    return commits, files


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
