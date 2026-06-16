"""H1 — Live MCP protocol tests.

Uses fastmcp.Client for real MCP protocol round-trips against the in-memory
soma server. No Claude Desktop needed — this is the gate that converts
"asserted" to "verified" for P2.1.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import NOW, make_repo, write_registry
from soma.mcp import mcp

SECRET = "sk-" + "0" * 40  # placeholder, not a real key — split + zero-entropy to avoid scanner false positives


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_tools():
    async def _run():
        from fastmcp import Client
        async with Client(mcp) as c:
            return await c.list_tools()
    return asyncio.run(_run())


def _call(tool: str, args: dict | None = None) -> object:
    """Call a tool; returns the CallToolResult."""
    async def _run():
        from fastmcp import Client
        async with Client(mcp) as c:
            return await c.call_tool(tool, args or {})
    return asyncio.run(_run())


def _text(result) -> str:
    """Extract string text from CallToolResult."""
    return result.data


# ---------------------------------------------------------------------------
# Tool list — protocol layer
# ---------------------------------------------------------------------------

class TestProtocolListTools:
    def test_four_tools_via_protocol(self) -> None:
        tools = _list_tools()
        assert len(tools) == 4

    def test_tool_names_via_protocol(self) -> None:
        names = {t.name for t in _list_tools()}
        assert names == {"list_projects", "get_context", "search_projects", "get_briefing"}

    def test_get_context_schema_has_project(self) -> None:
        tool = next(t for t in _list_tools() if t.name == "get_context")
        props = tool.inputSchema.get("properties", {})
        assert "project" in props

    def test_search_projects_schema_has_keyword(self) -> None:
        tool = next(t for t in _list_tools() if t.name == "search_projects")
        props = tool.inputSchema.get("properties", {})
        assert "keyword" in props

    def test_required_fields_get_context(self) -> None:
        tool = next(t for t in _list_tools() if t.name == "get_context")
        assert "project" in tool.inputSchema.get("required", [])

    def test_required_fields_search_projects(self) -> None:
        tool = next(t for t in _list_tools() if t.name == "search_projects")
        assert "keyword" in tool.inputSchema.get("required", [])

    def test_list_projects_no_required_params(self) -> None:
        tool = next(t for t in _list_tools() if t.name == "list_projects")
        assert tool.inputSchema.get("required", []) == []

    def test_get_briefing_no_required_params(self) -> None:
        tool = next(t for t in _list_tools() if t.name == "get_briefing")
        assert tool.inputSchema.get("required", []) == []


# ---------------------------------------------------------------------------
# Call round-trips — empty registry
# ---------------------------------------------------------------------------

class TestProtocolEmptyRegistry:
    def _patch(self, tmp_path, monkeypatch):
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))

    def test_list_projects_empty(self, tmp_path, monkeypatch) -> None:
        self._patch(tmp_path, monkeypatch)
        r = _call("list_projects")
        assert not r.is_error
        assert "No projects" in _text(r)

    def test_get_context_empty(self, tmp_path, monkeypatch) -> None:
        self._patch(tmp_path, monkeypatch)
        r = _call("get_context", {"project": "alpha"})
        assert not r.is_error
        assert "No projects" in _text(r)

    def test_get_briefing_empty(self, tmp_path, monkeypatch) -> None:
        self._patch(tmp_path, monkeypatch)
        r = _call("get_briefing")
        assert not r.is_error
        assert "No projects" in _text(r)

    def test_search_projects_empty(self, tmp_path, monkeypatch) -> None:
        self._patch(tmp_path, monkeypatch)
        r = _call("search_projects", {"keyword": "anything"})
        assert not r.is_error
        assert "No projects" in _text(r)


# ---------------------------------------------------------------------------
# Call round-trips — real project
# ---------------------------------------------------------------------------

class TestProtocolCallTools:
    def _setup(self, tmp_path, monkeypatch):
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        return reg

    def test_list_projects_returns_name(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        r = _call("list_projects")
        assert not r.is_error
        assert "alpha" in _text(r)

    def test_list_projects_has_headers(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        r = _call("list_projects")
        txt = _text(r)
        assert "Project" in txt
        assert "Branch" in txt

    def test_get_context_returns_summary(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        r = _call("get_context", {"project": "alpha"})
        assert not r.is_error
        txt = _text(r)
        assert "alpha" in txt
        assert "## Recent work" in txt

    def test_get_context_unknown_project_no_error(self, tmp_path, monkeypatch) -> None:
        """Unknown project MUST return a user-facing string, NOT a protocol error."""
        self._setup(tmp_path, monkeypatch)
        r = _call("get_context", {"project": "ghost"})
        assert not r.is_error, "unknown project must not raise a protocol error"
        txt = _text(r)
        assert "Unknown project" in txt
        assert "alpha" in txt  # lists known projects

    def test_get_context_within_token_budget(self, tmp_path, monkeypatch) -> None:
        from soma.context import estimate_tokens
        self._setup(tmp_path, monkeypatch)
        r = _call("get_context", {"project": "alpha"})
        assert estimate_tokens(_text(r)) <= 600

    def test_search_projects_finds_keyword(self, tmp_path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: unicorn", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        r = _call("search_projects", {"keyword": "unicorn"})
        assert not r.is_error
        assert "unicorn" in _text(r)
        assert "alpha" in _text(r)

    def test_search_projects_no_match(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        r = _call("search_projects", {"keyword": "xyzzy-not-found"})
        assert not r.is_error
        assert "No matches" in _text(r)

    def test_search_projects_case_insensitive(self, tmp_path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: UPPERCASE", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        r = _call("search_projects", {"keyword": "uppercase"})
        assert "alpha" in _text(r)

    def test_get_briefing_returns_header(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        r = _call("get_briefing")
        assert not r.is_error
        assert "Briefing" in _text(r)

    def test_get_briefing_includes_project(self, tmp_path, monkeypatch) -> None:
        self._setup(tmp_path, monkeypatch)
        r = _call("get_briefing")
        assert "alpha" in _text(r)


# ---------------------------------------------------------------------------
# Redaction through the protocol layer
# ---------------------------------------------------------------------------

class TestProtocolRedaction:
    """Secret planted in commit message must emerge as [REDACTED] through MCP."""

    def _setup_with_secret(self, tmp_path, monkeypatch):
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", f"feat: update api_key={SECRET}", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        return reg

    def test_get_context_redacts_api_key(self, tmp_path, monkeypatch) -> None:
        self._setup_with_secret(tmp_path, monkeypatch)
        r = _call("get_context", {"project": "alpha"})
        txt = _text(r)
        assert SECRET not in txt
        assert "[REDACTED]" in txt

    def test_search_projects_redacts_secret(self, tmp_path, monkeypatch) -> None:
        self._setup_with_secret(tmp_path, monkeypatch)
        # search for "update" — hits the commit; result must not expose the secret
        r = _call("search_projects", {"keyword": "update"})
        txt = _text(r)
        assert SECRET not in txt

    def test_get_briefing_no_secret_leak(self, tmp_path, monkeypatch) -> None:
        self._setup_with_secret(tmp_path, monkeypatch)
        r = _call("get_briefing")
        assert SECRET not in _text(r)

    def test_sk_key_pattern_redacted(self, tmp_path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(reg))
        alpha = tmp_path / "alpha"
        sk = "sk-" + "x" * 36
        make_repo(alpha, [("a.py", f"feat: set key {sk}", NOW - timedelta(hours=1))])
        write_registry(reg, {"alpha": alpha})
        r = _call("get_context", {"project": "alpha"})
        assert sk not in _text(r)
        assert "[REDACTED]" in _text(r)
