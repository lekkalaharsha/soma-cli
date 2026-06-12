"""Tests for P2.3 — tags, groups, archive."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app
from soma.detect import (
    add_tag, get_tags, is_archived, projects_by_tag,
    remove_tag, set_archived,
)

runner = CliRunner()


class TestTagCRUD:
    def test_add_tag(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        root = tmp_path / "alpha"
        root.mkdir()
        write_registry(p, {"alpha": root})
        assert add_tag("alpha", "work", p) is True
        assert "work" in get_tags("alpha", p)

    def test_add_tag_idempotent(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha"})
        add_tag("alpha", "work", p)
        add_tag("alpha", "work", p)
        assert get_tags("alpha", p).count("work") == 1

    def test_add_multiple_tags(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha"})
        add_tag("alpha", "work", p)
        add_tag("alpha", "python", p)
        tags = get_tags("alpha", p)
        assert "work" in tags and "python" in tags

    def test_remove_tag(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha"})
        add_tag("alpha", "work", p)
        assert remove_tag("alpha", "work", p) is True
        assert "work" not in get_tags("alpha", p)

    def test_remove_nonexistent_tag_returns_false(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha"})
        assert remove_tag("alpha", "ghost", p) is False

    def test_add_tag_unknown_project_returns_false(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        assert add_tag("ghost", "work", p) is False

    def test_get_tags_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha"})
        assert get_tags("alpha", p) == []

    def test_tags_isolated_per_project(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha", "beta": tmp_path / "beta"})
        add_tag("alpha", "work", p)
        assert "work" not in get_tags("beta", p)

    def test_projects_by_tag(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha", "beta": tmp_path / "beta", "gamma": tmp_path / "gamma"})
        add_tag("alpha", "work", p)
        add_tag("beta", "work", p)
        result = projects_by_tag("work", p)
        assert set(result.keys()) == {"alpha", "beta"}
        assert "gamma" not in result


class TestArchive:
    def test_archive_project(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha"})
        assert set_archived("alpha", True, p) is True
        assert is_archived("alpha", p) is True

    def test_unarchive_project(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha"})
        set_archived("alpha", True, p)
        set_archived("alpha", False, p)
        assert is_archived("alpha", p) is False

    def test_archive_unknown_returns_false(self, tmp_path: Path) -> None:
        assert set_archived("ghost", True, tmp_path / "p.toml") is False

    def test_not_archived_by_default(self, tmp_path: Path) -> None:
        p = tmp_path / "projects.toml"
        write_registry(p, {"alpha": tmp_path / "alpha"})
        assert is_archived("alpha", p) is False


class TestTagCLI:
    def test_tag_add(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["tag", "alpha", "work"])
        assert result.exit_code == 0, result.output
        assert "work" in result.output
        assert "Traceback" not in result.output

    def test_tag_list(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.cli as cli_mod
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        add_tag("alpha", "python", registry)
        result = runner.invoke(app, ["tag", "alpha", "--list"])
        assert result.exit_code == 0, result.output
        assert "python" in result.output

    def test_tag_remove(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.detect as det
        import soma.cli as cli_mod
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        add_tag("alpha", "work", registry)
        result = runner.invoke(app, ["tag", "alpha", "--remove", "work"])
        assert result.exit_code == 0, result.output
        assert "Removed" in result.output

    def test_tag_unknown_project_fails(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["tag", "ghost", "work"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output


class TestArchiveCLI:
    def test_archive_command(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["archive", "alpha"])
        assert result.exit_code == 0, result.output
        assert "Archived" in result.output
        assert "Traceback" not in result.output

    def test_unarchive_command(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        runner.invoke(app, ["archive", "alpha"])
        result = runner.invoke(app, ["unarchive", "alpha"])
        assert result.exit_code == 0, result.output
        assert "Restored" in result.output

    def test_archive_unknown_fails(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["archive", "ghost"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_briefing_hides_archived(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        beta = tmp_path / "beta"
        make_repo(beta, [("b.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha, "beta": beta})
        # archive beta
        import soma.detect as det
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        set_archived("beta", True, registry)
        result = runner.invoke(app, ["briefing"])
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output
        assert "beta" not in result.output

    def test_briefing_all_shows_archived(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        import soma.detect as det
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        set_archived("alpha", True, registry)
        result = runner.invoke(app, ["briefing", "--all"])
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output


class TestGroupContext:
    def test_group_context(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        import soma.detect as det
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        alpha = tmp_path / "alpha"
        beta = tmp_path / "beta"
        make_repo(alpha, [("a.py", "feat: alpha work", NOW - timedelta(hours=1))])
        make_repo(beta, [("b.py", "feat: beta work", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha, "beta": beta})
        add_tag("alpha", "frontend", registry)
        add_tag("beta", "frontend", registry)
        result = runner.invoke(app, ["context", "--group", "frontend"])
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output
        assert "beta" in result.output
        assert "---" in result.output  # separator between contexts

    def test_group_context_unknown_tag_fails(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["context", "--group", "ghost-tag"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output
