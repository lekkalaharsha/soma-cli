"""Tests for soma/status.py — last activity, recent commits, files changed, CLI views.

Real git repos are built in tmp_path with controlled commit dates because the
shared fixture tree's repos are fake (.git contains only HEAD) — those fakes
are reused here to exercise the graceful non-git fallback and the perf gate.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import git
import pytest
import tomli_w
from typer.testing import CliRunner

import soma.cli
from soma.cli import app
from soma.status import get_status, humanize_delta

runner = CliRunner()

NOW = datetime.now(timezone.utc)


def make_repo(
    path: Path,
    commits: list[tuple[str, str, datetime]],
    branch: str = "main",
) -> git.Repo:
    """Create a real git repo with commits at controlled timestamps.

    commits: list of (filename, message, when) — applied oldest first.
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
    path = tmp_path / "soma-config" / "projects.toml"
    monkeypatch.setattr(soma.cli, "PROJECTS_FILE", path)
    return path


class TestStatusData:
    def test_last_active_prefers_git_when_newer(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "fresh"
        make_repo(repo_dir, [("a.py", "feat: new work", NOW)])
        set_tree_mtimes(repo_dir, NOW - timedelta(days=10))
        status = get_status("fresh", repo_dir)
        assert status.last_active is not None
        assert NOW - status.last_active < timedelta(minutes=5)

    def test_last_active_uses_mtime_when_newer(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "stale"
        # Commit is 10 days old, but write_text left the file's mtime at "now".
        make_repo(repo_dir, [("a.py", "feat: old work", NOW - timedelta(days=10))])
        status = get_status("stale", repo_dir)
        assert status.last_active is not None
        assert NOW - status.last_active < timedelta(minutes=5)

    def test_recent_commits_max_five_newest_first(self, tmp_path: Path) -> None:
        commits = [
            (f"f{i}.py", f"feat: change {i}", NOW - timedelta(hours=7 - i))
            for i in range(7)
        ]
        repo_dir = tmp_path / "busy"
        make_repo(repo_dir, commits)
        status = get_status("busy", repo_dir)
        assert len(status.recent_commits) == 5
        messages = [c.message for c in status.recent_commits]
        assert messages == [f"feat: change {i}" for i in (6, 5, 4, 3, 2)]

    def test_files_changed_7d_unique_paths(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "dup"
        make_repo(
            repo_dir,
            [
                ("a.py", "feat: first touch", NOW - timedelta(days=2)),
                ("a.py", "fix: second touch", NOW - timedelta(days=1)),
                ("b.py", "feat: other file", NOW - timedelta(hours=1)),
            ],
        )
        status = get_status("dup", repo_dir)
        assert status.files_changed_7d.count("a.py") == 1
        assert sorted(status.files_changed_7d) == ["a.py", "b.py"]

    def test_files_changed_7d_filters_noise(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "noisy"
        make_repo(
            repo_dir,
            [
                ("src/app.py", "feat: app", NOW - timedelta(hours=2)),
                ("debug.log", "chore: committed a log", NOW - timedelta(hours=1)),
            ],
        )
        status = get_status("noisy", repo_dir)
        assert "src/app.py" in status.files_changed_7d
        assert "debug.log" not in status.files_changed_7d

    def test_files_changed_7d_excludes_old_commits(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "old"
        make_repo(repo_dir, [("a.py", "feat: ancient", NOW - timedelta(days=30))])
        status = get_status("old", repo_dir)
        assert status.files_changed_7d == []


class TestHumanize:
    def test_buckets(self) -> None:
        now = datetime.now(timezone.utc)
        assert humanize_delta(now, now=now) == "just now"
        assert humanize_delta(now - timedelta(minutes=5), now=now) == "5m ago"
        assert humanize_delta(now - timedelta(hours=2), now=now) == "2h ago"
        assert humanize_delta(now - timedelta(days=3), now=now) == "3d ago"
        assert humanize_delta(None, now=now) == "—"


class TestStatusCli:
    def test_all_projects_table_columns(self, tmp_path: Path, registry: Path) -> None:
        make_repo(tmp_path / "alpha", [("a.py", "feat: a", NOW - timedelta(hours=1))])
        make_repo(tmp_path / "beta", [("b.py", "feat: b", NOW - timedelta(days=3))])
        write_registry(
            registry, {"alpha": tmp_path / "alpha", "beta": tmp_path / "beta"}
        )
        result = runner.invoke(app, ["status"], env={"COLUMNS": "200"})
        assert result.exit_code == 0, result.output
        for column in ("Project", "Last Active", "Branch", "Commits", "Files (7d)"):
            assert column in result.output
        assert "alpha" in result.output
        assert "beta" in result.output

    def test_all_projects_sorted_most_recent_first(
        self, tmp_path: Path, registry: Path
    ) -> None:
        make_repo(tmp_path / "older", [("a.py", "feat: a", NOW - timedelta(days=5))])
        set_tree_mtimes(tmp_path / "older", NOW - timedelta(days=5))
        make_repo(tmp_path / "newer", [("b.py", "feat: b", NOW - timedelta(hours=1))])
        write_registry(
            registry, {"older": tmp_path / "older", "newer": tmp_path / "newer"}
        )
        result = runner.invoke(app, ["status"], env={"COLUMNS": "200"})
        assert result.exit_code == 0, result.output
        assert result.output.index("newer") < result.output.index("older")

    def test_deep_view(self, tmp_path: Path, registry: Path) -> None:
        make_repo(
            tmp_path / "deep",
            [
                ("docs/trade_study.md", "docs: trade study", NOW - timedelta(days=3)),
                ("src/radar.py", "fix: radar param matrix", NOW - timedelta(hours=3)),
            ],
            branch="phase1-trade-study",
        )
        write_registry(registry, {"deep": tmp_path / "deep"})
        result = runner.invoke(app, ["status", "deep"], env={"COLUMNS": "200"})
        assert result.exit_code == 0, result.output
        assert "phase1-trade-study" in result.output
        assert "fix: radar param matrix" in result.output
        assert "docs: trade study" in result.output
        assert "src/radar.py" in result.output
        assert "Branch" in result.output
        assert "Last active" in result.output

    def test_unknown_project_clean_error(
        self, tmp_path: Path, registry: Path
    ) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["status", "ghost"])
        assert result.exit_code == 1
        assert "ghost" in result.output
        assert "Traceback" not in result.output

    def test_non_git_project_graceful(self, tmp_path: Path, registry: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        (plain / "notes.md").write_text("just notes\n")
        write_registry(registry, {"plain": plain})
        result = runner.invoke(app, ["status", "plain"], env={"COLUMNS": "200"})
        assert result.exit_code == 0, result.output
        assert "plain" in result.output
        assert "Traceback" not in result.output

    def test_performance_under_2s_with_fixture_tree(
        self, fixture_home: Path, registry: Path, tmp_path: Path
    ) -> None:
        roots = {
            "repo_a": fixture_home / "repo_a",
            "repo_b": fixture_home / "repo_b",
            "repo_c": fixture_home / "nested" / "repo_c",
            "repo_deep4": fixture_home / "l1" / "l2" / "l3" / "repo_deep4",
        }
        for i in range(2):
            real = tmp_path / f"real_{i}"
            make_repo(
                real,
                [
                    (f"f{j}.py", f"feat: change {j}", NOW - timedelta(hours=j + 1))
                    for j in range(5)
                ],
            )
            roots[f"real_{i}"] = real
        write_registry(registry, roots)
        start = time.perf_counter()
        result = runner.invoke(app, ["status"], env={"COLUMNS": "200"})
        elapsed = time.perf_counter() - start
        assert result.exit_code == 0, result.output
        assert elapsed < 2.0, f"soma status took {elapsed:.2f}s"
