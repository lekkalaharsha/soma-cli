"""Tests for P2.4 — context --format json, soma diff, soma doctor, soma hook."""
from __future__ import annotations

import json
import os
import stat
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app, _BASELINES_DIR
from soma.context import generate_context_dict

runner = CliRunner()


# ---------------------------------------------------------------------------
# generate_context_dict
# ---------------------------------------------------------------------------
class TestGenerateContextDict:
    def test_returns_dict(self, tmp_path: Path) -> None:
        make_repo(tmp_path / "alpha", [("a.py", "feat: init", NOW - timedelta(hours=1))])
        d = generate_context_dict("alpha", tmp_path / "alpha")
        assert isinstance(d, dict)

    def test_required_keys(self, tmp_path: Path) -> None:
        make_repo(tmp_path / "alpha", [("a.py", "feat: init", NOW - timedelta(hours=1))])
        d = generate_context_dict("alpha", tmp_path / "alpha")
        for key in ("project", "branch", "confidence", "recent_commits", "files_in_motion", "blockers", "focus"):
            assert key in d, f"missing key: {key}"

    def test_project_name(self, tmp_path: Path) -> None:
        make_repo(tmp_path / "alpha", [("a.py", "feat: init", NOW - timedelta(hours=1))])
        d = generate_context_dict("alpha", tmp_path / "alpha")
        assert d["project"] == "alpha"

    def test_recent_commits_structure(self, tmp_path: Path) -> None:
        make_repo(tmp_path / "alpha", [("a.py", "feat: hello", NOW - timedelta(hours=1))])
        d = generate_context_dict("alpha", tmp_path / "alpha")
        assert len(d["recent_commits"]) >= 1
        c = d["recent_commits"][0]
        assert "message" in c and "when" in c

    def test_json_serialisable(self, tmp_path: Path) -> None:
        make_repo(tmp_path / "alpha", [("a.py", "feat: init", NOW - timedelta(hours=1))])
        d = generate_context_dict("alpha", tmp_path / "alpha")
        serialised = json.dumps(d)
        assert json.loads(serialised)["project"] == "alpha"

    def test_empty_repo(self, tmp_path: Path) -> None:
        # non-git dir — should not raise
        (tmp_path / "empty").mkdir()
        d = generate_context_dict("empty", tmp_path / "empty")
        assert d["project"] == "empty"


# ---------------------------------------------------------------------------
# context --format json via CLI
# ---------------------------------------------------------------------------
class TestContextFormatJson:
    def test_json_output(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["context", "alpha", "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["project"] == "alpha"
        assert "branch" in data

    def test_json_has_required_keys(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["context", "alpha", "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        for key in ("project", "branch", "confidence", "recent_commits", "blockers", "focus"):
            assert key in data

    def test_invalid_format_fails(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["context", "alpha", "--format", "xml"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_group_json_returns_list(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.cli as cli_mod
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        alpha = tmp_path / "alpha"
        beta = tmp_path / "beta"
        make_repo(alpha, [("a.py", "feat: alpha", NOW - timedelta(hours=1))])
        make_repo(beta, [("b.py", "feat: beta", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha, "beta": beta})
        from soma.detect import add_tag
        add_tag("alpha", "grp", registry)
        add_tag("beta", "grp", registry)
        result = runner.invoke(app, ["context", "--group", "grp", "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2


# ---------------------------------------------------------------------------
# soma diff
# ---------------------------------------------------------------------------
class TestDiff:
    def _save_baseline(self, name: str, root: Path, baselines_dir: Path) -> None:
        from soma.context import generate_context
        baselines_dir.mkdir(parents=True, exist_ok=True)
        import re
        safe = re.sub(r"[^\w\-]", "_", name)
        text = generate_context(name, root)
        (baselines_dir / f"{safe}.md").write_text(text, encoding="utf-8", newline="\n")

    def test_diff_no_baseline_fails(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        baselines = tmp_path / "baselines"
        monkeypatch.setattr(cli_mod, "_BASELINES_DIR", baselines)
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["diff", "alpha"])
        assert result.exit_code == 1
        assert "baseline" in result.output.lower()
        assert "Traceback" not in result.output

    def test_diff_no_change(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        baselines = tmp_path / "baselines"
        monkeypatch.setattr(cli_mod, "_BASELINES_DIR", baselines)
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        self._save_baseline("alpha", alpha, baselines)
        result = runner.invoke(app, ["diff", "alpha"])
        assert result.exit_code == 0, result.output
        assert "no change" in result.output.lower()
        assert "Traceback" not in result.output

    def test_diff_unknown_project_fails(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["diff", "ghost"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# soma doctor
# ---------------------------------------------------------------------------
class TestDoctor:
    def test_doctor_empty_registry(self, registry: Path, tmp_path: Path) -> None:
        # registry fixture points at a temp registry that does not exist yet
        result = runner.invoke(app, ["doctor"])
        # no registered projects → ok (just warns)
        assert "Traceback" not in result.output

    def test_doctor_valid_repo_passes(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["doctor"])
        assert "Traceback" not in result.output
        assert "all registered roots exist" in result.output

    def test_doctor_stale_root_detected(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"ghost": tmp_path / "ghost-dir-does-not-exist"})
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "stale" in result.output.lower()
        assert "Traceback" not in result.output

    def test_doctor_non_git_root(self, registry: Path, tmp_path: Path) -> None:
        bare = tmp_path / "bare"
        bare.mkdir()
        (bare / "file.py").write_text("x")
        write_registry(registry, {"bare": bare})
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "non-git" in result.output
        assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# soma hook install / remove
# ---------------------------------------------------------------------------
class TestHookInstall:
    def test_hook_install_creates_file(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["hook", "install", "alpha"])
        assert result.exit_code == 0, result.output
        hook = alpha / ".git" / "hooks" / "post-commit"
        assert hook.exists()
        assert "soma context alpha" in hook.read_text(encoding="utf-8")
        assert "Traceback" not in result.output

    def test_hook_install_unknown_project_fails(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["hook", "install", "ghost"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_hook_remove_deletes_file(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        runner.invoke(app, ["hook", "install", "alpha"])
        result = runner.invoke(app, ["hook", "remove", "alpha"])
        assert result.exit_code == 0, result.output
        assert not (alpha / ".git" / "hooks" / "post-commit").exists()
        assert "Traceback" not in result.output

    def test_hook_remove_no_hook_is_ok(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["hook", "remove", "alpha"])
        assert result.exit_code == 0, result.output
        assert "Traceback" not in result.output

    def test_hook_remove_foreign_hook_refuses(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        hook = alpha / ".git" / "hooks" / "post-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\necho 'not soma'\n", encoding="utf-8")
        result = runner.invoke(app, ["hook", "remove", "alpha"])
        assert result.exit_code == 1
        assert hook.exists()  # not deleted
        assert "Traceback" not in result.output

    def test_hook_install_foreign_hook_refuses(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        hook = alpha / ".git" / "hooks" / "post-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\necho 'existing hook'\n", encoding="utf-8")
        result = runner.invoke(app, ["hook", "install", "alpha"])
        assert result.exit_code == 1
        assert "not from soma" in result.output or "manually" in result.output
        assert "Traceback" not in result.output
