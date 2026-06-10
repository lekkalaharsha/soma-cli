"""Tests for soma.filters — the noise wall.

Filter rules live ONLY in soma/filters.py (CLAUDE.md contract).
"""
from pathlib import Path

import pytest

from soma.filters import is_watched, should_ignore


class TestShouldIgnore:
    @pytest.mark.parametrize(
        "path",
        [
            "project/__pycache__/mod.cpython-312.pyc",
            "web/node_modules/react/index.js",  # the node_modules trap
            "node_modules/left-pad/index.js",
            ".git/objects/ab/cdef0123",
            "repo/.git/objects/pack/pack-1.idx",
            "repo/.venv/lib/python3.12/site-packages/x.py",
            "dist/soma_cli-0.1.0-py3-none-any.whl",
            "build/lib/soma/cli.py",
            ".cache/pip/wheels/x",
            "soma/module.pyc",
            "logs/debug.log",
        ],
    )
    def test_noise_is_ignored(self, path: str) -> None:
        assert should_ignore(path) is True
        assert should_ignore(Path(path)) is True  # Path input too

    @pytest.mark.parametrize(
        "path",
        [
            "soma/cli.py",
            "README.md",
            ".git/HEAD",  # only .git/objects is noise, not all of .git
            "distribution/notes.md",  # 'dist' must match a whole segment
            "builder/main.py",  # 'build' must match a whole segment
            "docs/changelog.md",
            "src/distill.py",
        ],
    )
    def test_real_files_pass(self, path: str) -> None:
        assert should_ignore(path) is False


class TestIsWatched:
    @pytest.mark.parametrize(
        "path",
        [
            "soma/cli.py",
            "web/app.ts",
            "core/lib.rs",
            "cmd/main.go",
            "native/impl.c",
            "native/impl.cpp",
            "README.md",
            "ci/pipeline.yaml",
            "pyproject.toml",
            "data/config.json",
            "Dockerfile",
            "deploy/Dockerfile",
            "CMakeLists.txt",
            "src/CMakeLists.txt",
        ],
    )
    def test_watched_extensions_and_names(self, path: str) -> None:
        assert is_watched(path) is True
        assert is_watched(Path(path)) is True

    @pytest.mark.parametrize(
        "path",
        [
            "assets/photo.png",
            "bin/tool.exe",
            "soma/module.pyc",
            "notes.txt",
            "archive.tar.gz",
            "Makefile",  # not in the watch list for v1
        ],
    )
    def test_unwatched_files(self, path: str) -> None:
        assert is_watched(path) is False
