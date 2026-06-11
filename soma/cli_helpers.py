"""Framework-agnostic helpers for the CLI — no typer/rich, easy to unit test.

Kept separate from cli.py so the command surface stays focused on argument
parsing and orchestration. cli.py re-exports these names, so tests and lazy
imports that reference ``soma.cli._copy_to_clipboard`` etc. keep working.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from soma.filters import is_watched, should_ignore
from soma.status import ProjectStatus


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    plat = platform.system()
    try:
        if plat == "Windows":
            subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True, capture_output=True)
        elif plat == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, capture_output=True)
        else:
            # Linux: try xclip then xsel
            try:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True, capture_output=True)
            except FileNotFoundError:
                subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode("utf-8"), check=True, capture_output=True)
        return True
    except Exception:
        return False


def _parse_since(value: str) -> datetime:
    """Parse '2026-06-01', '7d', '2w', '3h', 'yesterday' → UTC datetime.

    Raises ValueError for unrecognised formats.
    """
    now = datetime.now(timezone.utc)
    v = value.strip().lower()
    if v == "yesterday":
        return now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    m = re.fullmatch(r"(\d+)(d|w|h)", v)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = {"d": timedelta(days=n), "w": timedelta(weeks=n), "h": timedelta(hours=n)}[unit]
        return now - delta
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    raise ValueError(
        f"Cannot parse '{value}'. Use YYYY-MM-DD, Nd (days), Nw (weeks), Nh (hours), or 'yesterday'."
    )


def _collect_mtimes(root: Path, max_depth: int = 3) -> dict[str, float]:
    """Return {abs_path: mtime} for watched files under root (for debounce)."""
    result: dict[str, float] = {}
    _mtime_walk(str(root), root, 0, max_depth, result)
    return result


def _mtime_walk(
    directory: str, root: Path, depth: int, max_depth: int, result: dict[str, float]
) -> None:
    if depth > max_depth:
        return
    try:
        with os.scandir(directory) as it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        if not should_ignore(e.name):
                            _mtime_walk(e.path, root, depth + 1, max_depth, result)
                    elif is_watched(e.name):
                        result[e.path] = e.stat(follow_symlinks=False).st_mtime
                except (OSError, ValueError):
                    continue
    except OSError:
        pass


def _status_to_dict(s: ProjectStatus) -> dict:
    return {
        "name": s.name,
        "branch": s.branch,
        "last_active": s.last_active.isoformat() if s.last_active else None,
        "commits_7d": s.commits_7d,
        "files_changed_7d": s.files_changed_7d,
        "recent_commits": [
            {"message": c.message, "when": c.when.isoformat()} for c in s.recent_commits
        ],
        "warning": s.warning,
    }


_CLAUDE_DESKTOP_CONFIG = {
    "Darwin": Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
    "Windows": Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json",
    "Linux": Path.home() / ".config" / "Claude" / "claude_desktop_config.json",
}


def _config_path() -> Path:
    system = platform.system()
    return _CLAUDE_DESKTOP_CONFIG.get(system, _CLAUDE_DESKTOP_CONFIG["Linux"])
