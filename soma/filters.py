"""Single source of truth for SOMA's noise-filtering rules.

Every other module must import should_ignore / is_watched from here —
never re-implement filter logic elsewhere (CLAUDE.md contract).
"""
from __future__ import annotations

import fnmatch
from pathlib import PurePath

# Directory names that are pure noise wherever they appear in a path.
IGNORE_DIRS: frozenset[str] = frozenset(
    {"__pycache__", "node_modules", ".venv", "dist", "build", ".cache"}
)

# Filename glob patterns that are noise.
IGNORE_FILE_PATTERNS: tuple[str, ...] = ("*.pyc", "*.log")

# Extensions that count as "real work" for activity tracking.
WATCH_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".rs", ".go", ".c", ".cpp", ".md", ".yaml", ".toml", ".json"}
)

# Exact filenames watched regardless of extension.
WATCH_FILENAMES: frozenset[str] = frozenset({"Dockerfile", "CMakeLists.txt"})


def should_ignore(path: str | PurePath) -> bool:
    """True if the path is build/dependency noise SOMA must never scan."""
    parts = PurePath(path).parts
    for i, part in enumerate(parts):
        if part in IGNORE_DIRS:
            return True
        # Only .git/objects is noise — .git itself holds the history we read.
        if part == ".git" and i + 1 < len(parts) and parts[i + 1] == "objects":
            return True
    if not parts:
        return False
    name = parts[-1]
    return any(fnmatch.fnmatch(name, pattern) for pattern in IGNORE_FILE_PATTERNS)


def is_watched(path: str | PurePath) -> bool:
    """True if the file counts as real work (source/docs/config)."""
    p = PurePath(path)
    if p.name in WATCH_FILENAMES:
        return True
    return p.suffix in WATCH_EXTENSIONS
