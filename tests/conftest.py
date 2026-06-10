"""Shared fixtures and repo-building helpers.

The fixture tree in tests/fixtures/home uses `_git` directory names because
git refuses to track files under a real `.git` directory. fixture_home copies
the tree to tmp_path and renames `_git` -> `.git` so detection sees real repos.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import git
import pytest
import tomli_w

FIXTURE_SRC = Path(__file__).parent / "fixtures" / "home"

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def fixture_home(tmp_path: Path) -> Path:
    dest = tmp_path / "home"
    shutil.copytree(FIXTURE_SRC, dest)
    # Deepest first so parent renames don't invalidate child paths.
    for git_dir in sorted(dest.rglob("_git"), key=lambda p: len(p.parts), reverse=True):
        git_dir.rename(git_dir.with_name(".git"))
    return dest


def make_repo(
    path: Path,
    commits: list[tuple[str, str, datetime]],
    branch: str = "main",
) -> git.Repo:
    """Create a real git repo with commits at controlled timestamps.

    commits: list of (filename, message, when) — applied in list order,
    so pass oldest first.
    """
    path.mkdir(parents=True, exist_ok=True)
    repo = git.Repo.init(path, initial_branch=branch)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "SOMA Test")
        cw.set_value("user", "email", "soma@test.local")
    for filename, message, when in commits:
        f = path / filename
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(message + "\n")
        repo.index.add([filename])
        stamp = f"{int(when.timestamp())} +0000"  # git raw date format
        repo.index.commit(message, author_date=stamp, commit_date=stamp)
    return repo


def set_tree_mtimes(root: Path, when: datetime) -> None:
    """Backdate every working-tree file/dir mtime (skips .git internals)."""
    ts = when.timestamp()
    for p in root.rglob("*"):
        if ".git" in p.parts:
            continue
        os.utime(p, (ts, ts))


def write_registry(registry_path: Path, projects: dict[str, Path]) -> None:
    data = {
        "projects": {
            name: {
                "root": str(root),
                "git": True,
                "registered_at": NOW.isoformat(timespec="seconds"),
            }
            for name, root in projects.items()
        }
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("wb") as f:
        tomli_w.dump(data, f)


@pytest.fixture()
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import soma.cli

    path = tmp_path / "soma-config" / "projects.toml"
    monkeypatch.setattr(soma.cli, "PROJECTS_FILE", path)
    return path
