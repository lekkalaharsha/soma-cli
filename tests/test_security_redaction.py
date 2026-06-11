"""Security regression — no credential survives ANY render path.

CLAUDE.md hard gate: "Zero credentials in any soma output." Before this suite,
redact() guarded only `soma context` text. These tests plant a secret in a
commit message, a README, and a note, then assert it never appears in
status / history / context (text+json) / MCP output.
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app

runner = CliRunner()

SECRET = "sk-abcdefghij0123456789ABCDEFGHIJ0123456789"
SECRET_ASSIGN = "api_key=supersecretvalue123456"


def _repo_with_secret(tmp_path: Path) -> Path:
    root = tmp_path / "leaky"
    make_repo(
        root,
        [
            ("a.py", f"feat: wire auth {SECRET}", NOW - timedelta(hours=2)),
            ("b.py", f"fix: rotate {SECRET_ASSIGN}", NOW - timedelta(hours=1)),
        ],
    )
    (root / "README.md").write_text(
        f"# Leaky\n\nA service. Config: {SECRET_ASSIGN}\n", encoding="utf-8"
    )
    return root


def _assert_clean(output: str) -> None:
    assert SECRET not in output, "raw sk- token leaked"
    assert SECRET_ASSIGN not in output, "api_key= assignment leaked"
    assert "supersecretvalue123456" not in output, "secret value leaked"


class TestStatusRedaction:
    def test_status_deep_view(self, registry: Path, tmp_path: Path) -> None:
        root = _repo_with_secret(tmp_path)
        write_registry(registry, {"leaky": root})
        result = runner.invoke(app, ["status", "leaky"])
        assert result.exit_code == 0, result.output
        _assert_clean(result.output)

    def test_status_json(self, registry: Path, tmp_path: Path) -> None:
        root = _repo_with_secret(tmp_path)
        write_registry(registry, {"leaky": root})
        result = runner.invoke(app, ["status", "leaky", "--json"])
        assert result.exit_code == 0, result.output
        _assert_clean(result.output)
        # still valid JSON
        json.loads(result.output)


class TestHistoryRedaction:
    def test_history_text(self, registry: Path, tmp_path: Path) -> None:
        root = _repo_with_secret(tmp_path)
        write_registry(registry, {"leaky": root})
        result = runner.invoke(app, ["history", "leaky", "--days", "7"])
        assert result.exit_code == 0, result.output
        _assert_clean(result.output)

    def test_history_markdown(self, registry: Path, tmp_path: Path) -> None:
        root = _repo_with_secret(tmp_path)
        write_registry(registry, {"leaky": root})
        result = runner.invoke(app, ["history", "leaky", "--days", "7", "--markdown"])
        assert result.exit_code == 0, result.output
        _assert_clean(result.output)


class TestContextRedaction:
    def test_context_text(self, registry: Path, tmp_path: Path) -> None:
        root = _repo_with_secret(tmp_path)
        write_registry(registry, {"leaky": root})
        result = runner.invoke(app, ["context", "leaky"])
        assert result.exit_code == 0, result.output
        _assert_clean(result.output)

    def test_context_json(self, registry: Path, tmp_path: Path) -> None:
        root = _repo_with_secret(tmp_path)
        write_registry(registry, {"leaky": root})
        result = runner.invoke(app, ["context", "leaky", "--format", "json"])
        assert result.exit_code == 0, result.output
        _assert_clean(result.output)
        json.loads(result.output)


class TestNotesRedaction:
    def test_note_in_context_json(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.notes as notes_mod
        notes_file = tmp_path / "notes.toml"
        monkeypatch.setattr(notes_mod, "NOTES_FILE", notes_file)
        root = tmp_path / "p"
        make_repo(root, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"p": root})
        from soma.notes import add_note
        add_note("p", f"remember {SECRET}", path=notes_file)
        # generate_context_dict reads notes via load_notes default path; patch it
        from soma.context import generate_context_dict
        monkeypatch.setattr("soma.context.load_notes", lambda name: __import__("soma.notes", fromlist=["load_notes"]).load_notes(name, path=notes_file))
        data = generate_context_dict("p", root)
        _assert_clean(json.dumps(data))


class TestMcpRedaction:
    def test_mcp_get_context(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setattr(det, "PROJECTS_FILE", reg)
        monkeypatch.setattr(mcp_mod, "PROJECTS_FILE", reg)
        root = _repo_with_secret(tmp_path)
        write_registry(reg, {"leaky": root})
        from soma.mcp import get_context
        _assert_clean(get_context("leaky"))

    def test_mcp_search(self, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.mcp as mcp_mod
        reg = tmp_path / "projects.toml"
        monkeypatch.setattr(det, "PROJECTS_FILE", reg)
        monkeypatch.setattr(mcp_mod, "PROJECTS_FILE", reg)
        root = _repo_with_secret(tmp_path)
        write_registry(reg, {"leaky": root})
        from soma.mcp import search_projects
        # search for a word that appears near the secret commit
        _assert_clean(search_projects("rotate"))
