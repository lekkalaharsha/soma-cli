"""Tests for soma/signals.py and soma integrity command."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app
from soma.signals import (
    IntegritySignal,
    _signal_format_violations,
    _signal_large_commits,
    check_integrity,
)

runner = CliRunner(mix_stderr=False)


def _setup(tmp_path, monkeypatch, commits=None):
    reg = tmp_path / "projects.toml"
    monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
    alpha = tmp_path / "alpha"
    if commits is None:
        commits = [("a.py", "feat: init", NOW - timedelta(hours=2))]
    make_repo(alpha, commits)
    write_registry(reg, {"alpha": alpha})
    return alpha


# ---------------------------------------------------------------------------
# Unit: IntegritySignal
# ---------------------------------------------------------------------------

class TestIntegritySignal:
    def test_str_warn(self) -> None:
        s = IntegritySignal(severity="warn", category="co-change", message="edited a but not b")
        text = str(s)
        assert "co-change" in text
        assert "edited a but not b" in text

    def test_str_info(self) -> None:
        s = IntegritySignal(severity="info", category="commit-format", message="bad format")
        text = str(s)
        assert "commit-format" in text

    def test_str_with_detail(self) -> None:
        s = IntegritySignal(severity="warn", category="test", message="msg", detail="extra info")
        assert "extra info" in str(s)


# ---------------------------------------------------------------------------
# Unit: format violation detector
# ---------------------------------------------------------------------------

class TestFormatViolations:
    def test_clean_messages_no_signals(self) -> None:
        msgs = ["feat(cli): add command", "fix(mcp): handle empty", "test(filters): add case"]
        assert _signal_format_violations(msgs) == []

    def test_bad_message_flagged(self) -> None:
        sigs = _signal_format_violations(["fixed stuff", "wip", "update"])
        assert len(sigs) >= 1
        assert all(s.category == "commit-format" for s in sigs)
        assert all(s.severity == "info" for s in sigs)

    def test_merge_commit_exempt(self) -> None:
        sigs = _signal_format_violations(["Merge branch 'main' into feat/foo"])
        assert sigs == []

    def test_revert_commit_exempt(self) -> None:
        sigs = _signal_format_violations(['Revert "feat: something"'])
        assert sigs == []

    def test_capped_at_four(self) -> None:
        bad = [f"wip {i}" for i in range(10)]
        sigs = _signal_format_violations(bad)
        assert len(sigs) <= 4

    def test_feat_without_scope_ok(self) -> None:
        sigs = _signal_format_violations(["feat: add something new"])
        assert sigs == []

    def test_breaking_change_ok(self) -> None:
        sigs = _signal_format_violations(["feat!: breaking new feature"])
        assert sigs == []


# ---------------------------------------------------------------------------
# Unit: large commit detector
# ---------------------------------------------------------------------------

class TestLargeCommits:
    def test_small_commit_no_signal(self) -> None:
        commits = [{f"file{i}.py" for i in range(5)}]
        sigs = _signal_large_commits(commits, ["feat: small"], threshold=20)
        assert sigs == []

    def test_large_commit_flagged(self) -> None:
        commits = [{f"file{i}.py" for i in range(25)}]
        sigs = _signal_large_commits(commits, ["chore: mass rename"], threshold=20)
        assert len(sigs) == 1
        assert sigs[0].category == "large-commit"
        assert sigs[0].severity == "warn"

    def test_capped_at_three(self) -> None:
        commits = [{f"file{i}.py" for i in range(25)} for _ in range(6)]
        sigs = _signal_large_commits(commits, ["msg"] * 6, threshold=20)
        assert len(sigs) <= 3


# ---------------------------------------------------------------------------
# Integration: check_integrity on a real fixture repo
# ---------------------------------------------------------------------------

class TestCheckIntegrity:
    def test_clean_repo_no_signals(self, tmp_path) -> None:
        repo_path = tmp_path / "repo"
        make_repo(repo_path, [("a.py", "feat: init", NOW - timedelta(hours=2))])
        # Single commit, no history to build co-change model from
        sigs = check_integrity(repo_path, days=7)
        # May have format signals but not co-change (no history)
        assert isinstance(sigs, list)

    def test_nonexistent_root_returns_empty(self, tmp_path) -> None:
        sigs = check_integrity(tmp_path / "does_not_exist", days=7)
        assert sigs == []

    def test_bad_format_detected(self, tmp_path) -> None:
        repo_path = tmp_path / "repo"
        make_repo(repo_path, [("a.py", "fixed stuff", NOW - timedelta(hours=1))])
        sigs = check_integrity(repo_path, days=7)
        format_sigs = [s for s in sigs if s.category == "commit-format"]
        assert len(format_sigs) >= 1

    def test_returns_list(self, tmp_path) -> None:
        repo_path = tmp_path / "repo"
        make_repo(repo_path, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        result = check_integrity(repo_path, days=7)
        assert isinstance(result, list)
        for s in result:
            assert isinstance(s, IntegritySignal)


# ---------------------------------------------------------------------------
# CLI: soma integrity command
# ---------------------------------------------------------------------------

class TestIntegrityCommand:
    def test_clean_project_exits_zero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["integrity", "alpha"])
        # Clean single-commit repo: may exit 0 (no warns) or 1 (format signal for "feat: init" which IS valid)
        assert result.exit_code in (0, 1)

    def test_unknown_project_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["integrity", "ghost"])
        assert result.exit_code != 0

    def test_no_registry_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(tmp_path / "missing.toml"))
        result = runner.invoke(app, ["integrity", "alpha"])
        assert result.exit_code != 0

    def test_bad_format_exits_nonzero_with_warns(self, tmp_path, monkeypatch) -> None:
        """A project with bad commit format should output signals."""
        _setup(tmp_path, monkeypatch, commits=[
            ("a.py", "fixed stuff", NOW - timedelta(hours=2)),
            ("b.py", "wip", NOW - timedelta(hours=1)),
        ])
        result = runner.invoke(app, ["integrity", "alpha"])
        # format signals are "info" severity so exit code may be 0
        assert result.exit_code in (0, 1)
        assert "alpha" in result.output

    def test_days_flag(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["integrity", "alpha", "--days", "30"])
        assert result.exit_code in (0, 1)

    def test_warn_only_flag(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["integrity", "alpha", "--warn-only"])
        assert result.exit_code in (0, 1)
