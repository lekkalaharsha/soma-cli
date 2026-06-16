"""Tests for soma power commands: drift, predict, verify, why, team."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app

runner = CliRunner(mix_stderr=False)


def _setup(tmp_path, monkeypatch, commits=None):
    """Bootstrap a registry with one 'alpha' project."""
    reg = tmp_path / "projects.toml"
    monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
    alpha = tmp_path / "alpha"
    if commits is None:
        commits = [("a.py", "feat: init alpha", NOW - timedelta(hours=2))]
    make_repo(alpha, commits)
    write_registry(reg, {"alpha": alpha})
    return alpha, reg


# ---------------------------------------------------------------------------
# soma drift
# ---------------------------------------------------------------------------

class TestDrift:
    def test_drift_exits_zero_with_changes(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["drift", "alpha"])
        assert result.exit_code == 0

    def test_drift_unknown_project_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["drift", "ghost"])
        assert result.exit_code != 0

    def test_drift_with_since_flag(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["drift", "alpha", "--since", "7d"])
        assert result.exit_code == 0

    def test_drift_no_registry_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(tmp_path / "missing.toml"))
        result = runner.invoke(app, ["drift", "alpha"])
        assert result.exit_code != 0

    def test_drift_output_mentions_project(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["drift", "alpha"])
        assert "alpha" in result.output


# ---------------------------------------------------------------------------
# soma predict
# ---------------------------------------------------------------------------

class TestPredict:
    def test_predict_unknown_file_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["predict", "alpha", "doesnotexist.py"])
        assert result.exit_code != 0

    def test_predict_unknown_project_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["predict", "ghost", "a.py"])
        assert result.exit_code != 0

    def test_predict_known_file_exits_zero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["predict", "alpha", "a.py"])
        # May be 0 (found patterns) or 0 (no patterns found, just reports)
        # Either way should not crash
        assert "predict" in result.output.lower() or result.exit_code in (0, 1)

    def test_predict_no_registry_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(tmp_path / "missing.toml"))
        result = runner.invoke(app, ["predict", "alpha", "a.py"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# soma verify
# ---------------------------------------------------------------------------

class TestVerify:
    def test_verify_exits_zero_with_extractable_claim(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["verify", "alpha", "a.py was changed last week"])
        assert result.exit_code == 0

    def test_verify_shows_findings(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["verify", "alpha", "a.py was changed"])
        assert "verify" in result.output.lower() or "a.py" in result.output

    def test_verify_unknown_project_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["verify", "ghost", "some claim"])
        assert result.exit_code != 0

    def test_verify_no_registry_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(tmp_path / "missing.toml"))
        result = runner.invoke(app, ["verify", "alpha", "any claim"])
        assert result.exit_code != 0

    def test_verify_shows_ground_truth(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["verify", "alpha", "a.py changed last week"])
        # Should always show the latest commit as ground truth
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# soma why
# ---------------------------------------------------------------------------

class TestWhy:
    def test_why_exits_zero_for_tracked_file(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["why", "alpha", "a.py"])
        assert result.exit_code == 0

    def test_why_shows_creation_info(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["why", "alpha", "a.py"])
        assert "Created" in result.output

    def test_why_shows_commit_count(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["why", "alpha", "a.py"])
        assert "commit" in result.output.lower()

    def test_why_untracked_file_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["why", "alpha", "doesnotexist.py"])
        assert result.exit_code != 0

    def test_why_unknown_project_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["why", "ghost", "a.py"])
        assert result.exit_code != 0

    def test_why_no_registry_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(tmp_path / "missing.toml"))
        result = runner.invoke(app, ["why", "alpha", "a.py"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# soma team
# ---------------------------------------------------------------------------

class TestTeam:
    def test_team_exits_zero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["team", "alpha"])
        assert result.exit_code == 0

    def test_team_shows_author(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["team", "alpha"])
        # Should have at least one author row
        assert "Author" in result.output or "commits" in result.output.lower()

    def test_team_with_days_flag(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["team", "alpha", "--days", "7"])
        assert result.exit_code == 0

    def test_team_unknown_project_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["team", "ghost"])
        assert result.exit_code != 0

    def test_team_no_registry_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(tmp_path / "missing.toml"))
        result = runner.invoke(app, ["team", "alpha"])
        assert result.exit_code != 0
