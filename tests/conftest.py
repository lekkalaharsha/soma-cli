"""Shared fixtures.

The fixture tree in tests/fixtures/home uses `_git` directory names because
git refuses to track files under a real `.git` directory. fixture_home copies
the tree to tmp_path and renames `_git` -> `.git` so detection sees real repos.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURE_SRC = Path(__file__).parent / "fixtures" / "home"


@pytest.fixture()
def fixture_home(tmp_path: Path) -> Path:
    dest = tmp_path / "home"
    shutil.copytree(FIXTURE_SRC, dest)
    # Deepest first so parent renames don't invalidate child paths.
    for git_dir in sorted(dest.rglob("_git"), key=lambda p: len(p.parts), reverse=True):
        git_dir.rename(git_dir.with_name(".git"))
    return dest
