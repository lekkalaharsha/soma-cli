"""Tests for P2.1 — SOMA MCP server tools and CLI commands."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app, _config_path
from soma.mcp import get_briefing, get_context, list_projects, search_projects, mcp

runner = CliRunner()


# ---------------------------------------------------------------------------
# Tool: list_projects
# ---------------------------------------------------------------------------
class TestListProjects:
    def test_returns_string(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = list_projects()
        assert isinstance(result, str)
        assert "alpha" in result

    def test_empty_registry(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        result = list_projects()
        assert "No projects" in result

    def test_has_header(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = list_projects()
        assert "Project" in result
        assert "Branch" in result


# ---------------------------------------------------------------------------
# Tool: get_context
# ---------------------------------------------------------------------------
class TestGetContext:
    def test_returns_context_string(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = get_context("alpha")
        assert "alpha" in result
        assert "## Recent work" in result

    def test_unknown_project_returns_message(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = get_context("ghost")
        assert "Unknown project" in result
        assert "alpha" in result  # lists known projects

    def test_output_within_token_budget(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        from soma.context import estimate_tokens
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = get_context("alpha")
        assert estimate_tokens(result) <= 600

    def test_no_credentials_leaked(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = get_context("alpha")
        for pat in ("api_key=", "secret=", "Bearer ", "sk-", "ghp_"):
            assert pat not in result


# ---------------------------------------------------------------------------
# Tool: search_projects
# ---------------------------------------------------------------------------
class TestSearchProjects:
    def test_finds_keyword(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: unicorn", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = search_projects("unicorn")
        assert "alpha" in result
        assert "unicorn" in result

    def test_no_match_returns_message(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = search_projects("xyzzy-not-found")
        assert "No matches" in result

    def test_case_insensitive(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: UPPER", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = search_projects("upper")
        assert "alpha" in result


# ---------------------------------------------------------------------------
# Tool: get_briefing
# ---------------------------------------------------------------------------
class TestGetBriefing:
    def test_returns_string(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        result = get_briefing()
        assert isinstance(result, str)
        assert "Briefing" in result

    def test_empty_registry(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        result = get_briefing()
        assert "No projects" in result

    def test_excludes_archived(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        from soma.detect import set_archived
        set_archived("alpha", True, reg)
        result = get_briefing()
        assert "All projects are archived" in result


# ---------------------------------------------------------------------------
# MCP server object: tool schema
# ---------------------------------------------------------------------------
class TestMcpToolSchema:
    def _tools(self) -> list:
        import asyncio
        return asyncio.run(mcp.list_tools())

    def test_four_tools_registered(self) -> None:
        assert len(self._tools()) == 8

    def test_tool_names(self) -> None:
        names = {t.name for t in self._tools()}
        assert names == {
            "list_projects",
            "get_context",
            "search_projects",
            "get_briefing",
            "get_history",
            "get_diff",
            "get_drift",
            "get_predict",
        }

    def test_get_context_has_project_param(self) -> None:
        tool = next(t for t in self._tools() if t.name == "get_context")
        schema = tool.parameters
        assert "project" in schema.get("properties", {})


# ---------------------------------------------------------------------------
# CLI: soma mcp install / uninstall
# ---------------------------------------------------------------------------
class TestMcpCLI:
    def test_mcp_install_dry_run(self, registry: Path) -> None:
        result = runner.invoke(app, ["mcp", "install", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "soma" in result.output
        assert "Traceback" not in result.output

    def test_mcp_install_writes_config(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        cfg = tmp_path / "Claude" / "claude_desktop_config.json"
        monkeypatch.setattr(cli_mod, "_config_path", lambda: cfg)
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0, result.output
        assert cfg.exists()
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "soma" in data.get("mcpServers", {})

    def test_mcp_install_merges_existing(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        cfg = tmp_path / "Claude" / "claude_desktop_config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}), encoding="utf-8")
        monkeypatch.setattr(cli_mod, "_config_path", lambda: cfg)
        result = runner.invoke(app, ["mcp", "install"])
        assert result.exit_code == 0, result.output
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "other" in data["mcpServers"]
        assert "soma" in data["mcpServers"]

    def test_mcp_uninstall_removes_entry(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        cfg = tmp_path / "Claude" / "claude_desktop_config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"mcpServers": {"soma": {"command": "soma", "args": ["mcp", "start"]}}}), encoding="utf-8")
        monkeypatch.setattr(cli_mod, "_config_path", lambda: cfg)
        result = runner.invoke(app, ["mcp", "uninstall"])
        assert result.exit_code == 0, result.output
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "soma" not in data.get("mcpServers", {})

    def test_mcp_uninstall_no_config(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        monkeypatch.setattr(cli_mod, "_config_path", lambda: tmp_path / "nonexistent.json")
        result = runner.invoke(app, ["mcp", "uninstall"])
        assert result.exit_code == 0, result.output
        assert "Traceback" not in result.output
