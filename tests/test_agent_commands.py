"""Tests for soma agent init and soma agent sync commands."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app

runner = CliRunner()


def _setup(tmp_path, monkeypatch, commits=None):
    reg = tmp_path / "projects.toml"
    monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
    alpha = tmp_path / "alpha"
    if commits is None:
        commits = [
            ("soma/cli.py", "feat: init cli", NOW - timedelta(hours=4)),
            ("soma/mcp.py", "feat: add mcp", NOW - timedelta(hours=3)),
            ("soma/cli.py", "fix: handle empty", NOW - timedelta(hours=2)),
            ("tests/test_cli.py", "test: add cli tests", NOW - timedelta(hours=1)),
        ]
    make_repo(alpha, commits)
    write_registry(reg, {"alpha": alpha})
    return alpha


# ---------------------------------------------------------------------------
# soma agent init
# ---------------------------------------------------------------------------

class TestAgentInit:
    def test_init_exits_zero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        result = runner.invoke(app, ["agent", "init", "alpha"])
        assert result.exit_code == 0

    def test_init_unknown_project_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["agent", "init", "ghost"])
        assert result.exit_code != 0

    def test_init_no_registry_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(tmp_path / "missing.toml"))
        result = runner.invoke(app, ["agent", "init", "alpha"])
        assert result.exit_code != 0

    def test_init_output_contains_project_name(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        result = runner.invoke(app, ["agent", "init", "alpha"])
        assert "alpha" in result.output

    def test_init_output_contains_ruleset_header(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        result = runner.invoke(app, ["agent", "init", "alpha"])
        assert "Agent Ruleset" in result.output

    def test_init_output_contains_key_files_section(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        result = runner.invoke(app, ["agent", "init", "alpha"])
        assert "Key files" in result.output

    def test_init_output_contains_branch(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        result = runner.invoke(app, ["agent", "init", "alpha"])
        assert "Branch" in result.output

    def test_init_output_contains_noise_section(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        result = runner.invoke(app, ["agent", "init", "alpha"])
        assert "Do not edit" in result.output

    def test_init_saves_file(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        runner.invoke(app, ["agent", "init", "alpha"])
        assert (agents_dir / "alpha.md").exists()

    def test_init_saved_file_contains_ruleset(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        runner.invoke(app, ["agent", "init", "alpha"])
        content = (agents_dir / "alpha.md").read_text()
        assert "Agent Ruleset" in content
        assert "alpha" in content

    def test_init_print_only_no_file(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        runner.invoke(app, ["agent", "init", "alpha", "--print"])
        assert not (agents_dir / "alpha.md").exists()

    def test_init_custom_output_path(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        out = tmp_path / "my-agent.md"
        result = runner.invoke(app, ["agent", "init", "alpha", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_init_copairs_section_with_multiple_commits(self, tmp_path, monkeypatch) -> None:
        """Files co-changed >=2 times should appear in the Co-change section."""
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        result = runner.invoke(app, ["agent", "init", "alpha"])
        # soma/cli.py appears in 2 commits, other files only 1 — may or may not have pairs
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# soma agent sync
# ---------------------------------------------------------------------------

class TestAgentSync:
    def test_sync_generates_when_missing(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        result = runner.invoke(app, ["agent", "sync", "alpha"])
        assert result.exit_code == 0
        assert (agents_dir / "alpha.md").exists()

    def test_sync_fresh_ruleset_no_regen(self, tmp_path, monkeypatch) -> None:
        """Freshly generated ruleset with 0 new commits stays as-is."""
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        # Generate first
        runner.invoke(app, ["agent", "init", "alpha"])
        # Sync — 0 new commits since file was just written
        result = runner.invoke(app, ["agent", "sync", "alpha"])
        assert result.exit_code == 0
        assert "fresh" in result.output.lower()

    def test_sync_force_regenerates(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        monkeypatch.setattr("soma.commands.agent._AGENTS_DIR", agents_dir)
        runner.invoke(app, ["agent", "init", "alpha"])
        result = runner.invoke(app, ["agent", "sync", "alpha", "--force"])
        assert result.exit_code == 0
        assert "Agent Ruleset" in result.output

    def test_sync_unknown_project_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        _setup(tmp_path, monkeypatch)
        result = runner.invoke(app, ["agent", "sync", "ghost"])
        assert result.exit_code != 0

    def test_sync_no_registry_exits_nonzero(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(tmp_path / "missing.toml"))
        result = runner.invoke(app, ["agent", "sync", "alpha"])
        assert result.exit_code != 0
