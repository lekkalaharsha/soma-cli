"""Project detection: scan a directory tree for git repository roots.

Uses os.scandir with aggressive pruning (hidden dirs, filter rules, found
repos) so a ~50k-file home directory scans in well under the 5s gate.
"""
from __future__ import annotations

import os
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import tomli_w
from pydantic import BaseModel

from soma.filters import should_ignore
from soma.runtime import DEFAULT_REGISTRY_PATH, SOMA_DIR, registry_path

DEFAULT_MAX_DEPTH = 4
PROJECTS_FILE = DEFAULT_REGISTRY_PATH


class Project(BaseModel):
    name: str
    root: str  # absolute path as str — TOML has no path type
    git: bool = True
    registered_at: str  # ISO 8601


def find_git_roots(base: Path, max_depth: int = DEFAULT_MAX_DEPTH) -> list[Path]:
    """Return directories under base (inclusive) that contain a .git entry."""
    roots: list[Path] = []
    _scan(base.resolve(), depth=0, max_depth=max_depth, roots=roots)
    return roots


def find_project_roots(base: Path, max_depth: int = DEFAULT_MAX_DEPTH) -> list[Path]:
    """Return all non-ignored directories under base (git or not).

    Used when git is not installed — registers directories as projects
    so status/context can show filesystem activity.
    """
    roots: list[Path] = []
    _scan_all(base.resolve(), depth=0, max_depth=max_depth, roots=roots)
    return roots


def _scan(directory: Path, depth: int, max_depth: int, roots: list[Path]) -> None:
    try:
        with os.scandir(directory) as it:
            entries = list(it)
    except OSError:  # permission denied, vanished dir, junction loops
        return
    if any(e.name == ".git" for e in entries):
        roots.append(directory)
        return  # don't descend into repos — nested repos are noise in v1
    if depth >= max_depth:
        return
    for entry in entries:
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        if entry.name.startswith("."):
            continue
        if should_ignore(entry.name):
            continue
        _scan(Path(entry.path), depth + 1, max_depth, roots)


def _scan_all(directory: Path, depth: int, max_depth: int, roots: list[Path]) -> None:
    """Scan directories regardless of .git presence."""
    try:
        with os.scandir(directory) as it:
            entries = list(it)
    except OSError:
        return
    if any(e.name == ".git" for e in entries):
        roots.append(directory)
        return
    if depth == 0:
        root_candidates = [e for e in entries if e.is_dir(follow_symlinks=False)
                           and not e.name.startswith(".")
                           and not should_ignore(e.name)]
        for e in root_candidates:
            _scan_all_dirs(Path(e.path), depth + 1, max_depth, roots)
    elif depth < max_depth:
        _scan_all_dirs(directory, depth, max_depth, roots)


def _scan_all_dirs(directory: Path, depth: int, max_depth: int, roots: list[Path]) -> None:
    """Collect all non-hidden, non-ignored directories at this level."""
    try:
        with os.scandir(directory) as it:
            entries = list(it)
    except OSError:
        return
    has_nested_repo = any(e.name == ".git" for e in entries)
    if has_nested_repo:
        roots.append(directory)
        return
    roots.append(directory)
    if depth >= max_depth:
        return
    for entry in entries:
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        if entry.name.startswith("."):
            continue
        if should_ignore(entry.name):
            continue
        _scan_all_dirs(Path(entry.path), depth + 1, max_depth, roots)


def _registry_path(path: Path | None = None) -> Path:
    return path or registry_path()


def load_registry(path: Path | None = None) -> dict[str, dict]:
    """Load the [projects] table; empty dict if the file doesn't exist yet."""
    path = _registry_path(path)
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data.get("projects", {})


def register_projects(
    roots: list[Path], path: Path | None = None
) -> tuple[list[Project], list[Project]]:
    """Merge found roots into the registry. Returns (new, already_known).

    Existing entries are never wiped or overwritten; identity is the root
    path, and name collisions between different roots get a -N suffix.
    """
    path = _registry_path(path)
    registry = load_registry(path)
    roots_to_name = {entry["root"]: name for name, entry in registry.items()}

    new: list[Project] = []
    known: list[Project] = []
    for root in roots:
        root_str = str(root)
        if root_str in roots_to_name:
            name = roots_to_name[root_str]
            known.append(Project(name=name, **registry[name]))
            continue
        name = _unique_name(root.name, registry)
        project = Project(
            name=name,
            root=root_str,
            git=True,
            registered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        registry[name] = project.model_dump(exclude={"name"})
        roots_to_name[root_str] = name
        new.append(project)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump({"projects": registry}, f)
    return new, known


def forget_project(name: str, path: Path | None = None) -> bool:
    """Remove a named project from the registry. Returns True if found and removed."""
    path = _registry_path(path)
    registry = load_registry(path)
    if name not in registry:
        return False
    del registry[name]
    _save_registry(registry, path)
    return True


def rename_project(old: str, new: str, path: Path | None = None) -> bool:
    """Rename a project in the registry. Returns True on success, False if old not found."""
    path = _registry_path(path)
    registry = load_registry(path)
    if old not in registry:
        return False
    registry[new] = registry.pop(old)
    _save_registry(registry, path)
    return True


def add_tag(name: str, tag: str, path: Path | None = None) -> bool:
    """Add a tag to a project. Returns False if project not found."""
    path = _registry_path(path)
    registry = load_registry(path)
    if name not in registry:
        return False
    tags: list[str] = registry[name].get("tags", [])
    if tag not in tags:
        tags.append(tag)
        registry[name]["tags"] = tags
        _save_registry(registry, path)
    return True


def remove_tag(name: str, tag: str, path: Path | None = None) -> bool:
    """Remove a tag from a project. Returns False if project or tag not found."""
    path = _registry_path(path)
    registry = load_registry(path)
    if name not in registry:
        return False
    tags: list[str] = registry[name].get("tags", [])
    if tag not in tags:
        return False
    registry[name]["tags"] = [t for t in tags if t != tag]
    _save_registry(registry, path)
    return True


def get_tags(name: str, path: Path | None = None) -> list[str]:
    """Return tags for a project, empty list if none."""
    registry = load_registry(path)
    return registry.get(name, {}).get("tags", [])


def projects_by_tag(tag: str, path: Path | None = None) -> dict[str, dict]:
    """Return registry subset whose tags list contains tag."""
    return {n: e for n, e in load_registry(path).items() if tag in e.get("tags", [])}


def set_archived(name: str, archived: bool, path: Path | None = None) -> bool:
    """Set archived flag on a project. Returns False if not found."""
    path = _registry_path(path)
    registry = load_registry(path)
    if name not in registry:
        return False
    registry[name]["archived"] = archived
    _save_registry(registry, path)
    return True


def is_archived(name: str, path: Path | None = None) -> bool:
    registry = load_registry(path)
    return bool(registry.get(name, {}).get("archived", False))


def _save_registry(registry: dict[str, dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump({"projects": registry}, f)


def auto_scan(path: Path | None = None) -> int:
    """Scan home dir for new project roots and merge them silently.

    Returns the number of new projects registered. Skips when:
    - registry path is overridden by env var (test mode)
    - scan already ran in the last 30 seconds
    """
    import os as _os
    import shutil
    import time as _time

    scan_path = path or registry_path()
    if _os.environ.get("SOMA_PROJECTS_FILE"):
        return 0  # test mode — registry path is overridden

    # Throttle: don't re-scan more than once per 30s
    stamp_file = SOMA_DIR / ".last_scan"
    try:
        if stamp_file.exists() and _time.time() - stamp_file.stat().st_mtime < 30:
            return 0
    except OSError:
        pass

    base = Path.home()
    git_available = shutil.which("git") is not None
    if not base.is_dir():
        return 0
    existing = load_registry(scan_path)
    existing_roots = {e.get("root") for e in existing.values() if e.get("root")}

    if git_available:
        candidates = find_git_roots(base)
    else:
        candidates = find_project_roots(base)

    new_roots = [r for r in candidates if str(r) not in existing_roots]
    if not new_roots:
        try:
            stamp_file.parent.mkdir(parents=True, exist_ok=True)
            stamp_file.write_text("")
        except OSError:
            pass
        return 0

    new_projects, _ = register_projects(new_roots, scan_path)
    try:
        stamp_file.parent.mkdir(parents=True, exist_ok=True)
        stamp_file.write_text("")
    except OSError:
        pass
    return len(new_projects)


def _unique_name(base_name: str, registry: dict[str, dict]) -> str:
    if base_name not in registry:
        return base_name
    n = 2
    while f"{base_name}-{n}" in registry:
        n += 1
    return f"{base_name}-{n}"
