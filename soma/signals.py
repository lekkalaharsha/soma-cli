"""Commit pattern integrity signals — heuristic anomaly detection.

Reads git history to find deviations from established patterns:
  - Missing co-change partners (you edited A but forgot B)
  - Large commits (too many files in one shot)
  - Conventional commit format violations
  - Source changes without test coverage (when pattern exists)

No LLM, no network. Pure git log analysis.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from soma.filters import should_ignore

# Conventional commit prefix pattern
_CC_RE = re.compile(
    r"^(feat|fix|test|refactor|docs|chore|perf|style|ci|build|revert)"
    r"(\([a-z0-9\-]+\))?(!)?:\s+\S"
)

Severity = Literal["warn", "info"]


@dataclass
class IntegritySignal:
    severity: Severity
    category: str
    message: str
    detail: str = ""

    def __str__(self) -> str:
        prefix = "⚠" if self.severity == "warn" else "·"
        base = f"{prefix} [{self.category}] {self.message}"
        return f"{base}\n    {self.detail}" if self.detail else base


# ---------------------------------------------------------------------------
# Internal: build co-change model from full history
# ---------------------------------------------------------------------------

def _build_cochange_model(
    raw_log: str,
) -> dict[str, dict[str, int]]:
    """Parse git log output into co-occurrence counts.

    raw_log: output of `git log --name-only --pretty=format:---COMMIT---`
    Returns: {file: {partner: count_of_commits_touching_both}}
    """
    commits: list[set[str]] = []
    current: set[str] = set()
    for line in raw_log.splitlines():
        line = line.strip()
        if line == "---COMMIT---":
            if current:
                commits.append(current)
            current = set()
        elif line and not should_ignore(line):
            current.add(line)
    if current:
        commits.append(current)

    model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    touch_count: Counter = Counter()
    for commit in commits:
        files = list(commit)
        for f in files:
            touch_count[f] += 1
        for i, a in enumerate(files):
            for b in files[i + 1:]:
                model[a][b] += 1
                model[b][a] += 1

    return dict(model), touch_count


# ---------------------------------------------------------------------------
# Signal detectors
# ---------------------------------------------------------------------------

def _signal_missing_partners(
    recent_commits: list[set[str]],
    model: dict[str, dict[str, int]],
    touch_count: Counter,
    threshold: float = 0.75,
) -> list[IntegritySignal]:
    """Flag files edited recently where a high-confidence partner was skipped."""
    signals: list[IntegritySignal] = []
    recent_files: set[str] = set()
    for commit in recent_commits:
        recent_files |= commit

    for commit in recent_commits:
        for f in commit:
            partners = model.get(f, {})
            total_f = touch_count.get(f, 1)
            for partner, co_count in partners.items():
                confidence = co_count / total_f
                if confidence >= threshold and partner not in commit:
                    pct = int(confidence * 100)
                    signals.append(IntegritySignal(
                        severity="warn",
                        category="co-change",
                        message=f"edited `{f}` but not `{partner}` (co-changed {pct}% historically)",
                        detail=f"These files move together in {co_count}/{total_f} commits.",
                    ))
    # Deduplicate
    seen: set[str] = set()
    unique: list[IntegritySignal] = []
    for s in signals:
        if s.message not in seen:
            seen.add(s.message)
            unique.append(s)
    return unique[:6]  # cap to avoid noise


def _signal_large_commits(
    recent_commits: list[set[str]],
    recent_messages: list[str],
    threshold: int = 20,
) -> list[IntegritySignal]:
    """Flag commits that touched an unusually large number of files."""
    signals: list[IntegritySignal] = []
    for i, commit in enumerate(recent_commits):
        if len(commit) >= threshold:
            msg = recent_messages[i] if i < len(recent_messages) else "(unknown)"
            signals.append(IntegritySignal(
                severity="warn",
                category="large-commit",
                message=f"commit touches {len(commit)} files — consider splitting",
                detail=f"Commit: {msg[:72]}",
            ))
    return signals[:3]


def _signal_format_violations(
    recent_messages: list[str],
) -> list[IntegritySignal]:
    """Flag commits that don't follow conventional commit format."""
    signals: list[IntegritySignal] = []
    for msg in recent_messages:
        if msg.startswith("Merge ") or msg.startswith("Revert "):
            continue  # merge/revert commits are exempt
        if not _CC_RE.match(msg):
            signals.append(IntegritySignal(
                severity="info",
                category="commit-format",
                message="commit message doesn't follow conventional commit format",
                detail=f"Found: {msg[:72]}",
            ))
    return signals[:4]


def _signal_untested_changes(
    recent_commits: list[set[str]],
    model: dict[str, dict[str, int]],
    touch_count: Counter,
    threshold: float = 0.70,
) -> list[IntegritySignal]:
    """Flag source files changed without any test file in the same commit."""
    signals: list[IntegritySignal] = []
    for commit in recent_commits:
        has_test = any("test" in f.lower() or "spec" in f.lower() for f in commit)
        if has_test:
            continue
        for f in commit:
            if should_ignore(f) or "test" in f.lower():
                continue
            # Does this file historically co-change with a test file?
            partners = model.get(f, {})
            total_f = touch_count.get(f, 1)
            for partner, co_count in partners.items():
                if ("test" in partner.lower() or "spec" in partner.lower()):
                    confidence = co_count / total_f
                    if confidence >= threshold:
                        pct = int(confidence * 100)
                        signals.append(IntegritySignal(
                            severity="warn",
                            category="no-tests",
                            message=f"`{f}` changed without `{partner}` ({pct}% of past changes include tests)",
                            detail="Tests historically ship with this file.",
                        ))
                        break
    seen: set[str] = set()
    unique = []
    for s in signals:
        if s.message not in seen:
            seen.add(s.message)
            unique.append(s)
    return unique[:4]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_integrity(root: Path, days: int = 7) -> list[IntegritySignal]:
    """Run all integrity checks on recent commits of a git repo.

    Returns a list of IntegritySignals, empty if everything looks clean.
    """
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo  # noqa: PLC0415
    from git.exc import GitCommandError, GitCommandNotFound  # noqa: PLC0415

    try:
        repo = Repo(root)
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandNotFound):
        return []

    # Build full-history co-change model
    try:
        raw_full = repo.git.log("--name-only", "--pretty=format:---COMMIT---")
        model, touch_count = _build_cochange_model(raw_full)
    except (GitCommandError, GitCommandNotFound):
        return []

    # Collect recent commits (files + messages)
    try:
        raw_recent = repo.git.log(
            f"--since={days}.days.ago", "--name-only", "--pretty=format:MSG:%s"
        )
    except (GitCommandError, GitCommandNotFound):
        return []

    recent_commits: list[set[str]] = []
    recent_messages: list[str] = []
    current: set[str] = set()
    for line in raw_recent.splitlines():
        line = line.strip()
        if line.startswith("MSG:"):
            if current:
                recent_commits.append(current)
            current = set()
            recent_messages.append(line[4:])
        elif line and not should_ignore(line):
            current.add(line)
    if current:
        recent_commits.append(current)

    if not recent_commits:
        return []

    signals: list[IntegritySignal] = []
    signals += _signal_missing_partners(recent_commits, model, touch_count)
    signals += _signal_large_commits(recent_commits, recent_messages)
    signals += _signal_format_violations(recent_messages)
    signals += _signal_untested_changes(recent_commits, model, touch_count)
    return signals
