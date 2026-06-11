"""Tests for soma/notes.py — manual project annotations."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app
from soma.context import generate_context
from soma.notes import Note, add_note, clear_notes, load_notes, rename_notes

runner = CliRunner()


class TestNotesStorage:
    def test_add_and_load(self, tmp_path: Path) -> None:
        nf = tmp_path / "notes.toml"
        n = add_note("myproj", "blocked on infra access", nf)
        assert isinstance(n, Note)
        assert n.text == "blocked on infra access"
        notes = load_notes("myproj", nf)
        assert len(notes) == 1
        assert notes[0].text == "blocked on infra access"

    def test_multiple_notes_newest_first(self, tmp_path: Path) -> None:
        nf = tmp_path / "notes.toml"
        add_note("p", "first", nf)
        add_note("p", "second", nf)
        add_note("p", "third", nf)
        notes = load_notes("p", nf)
        assert notes[0].text == "third"
        assert notes[-1].text == "first"

    def test_load_empty_returns_empty(self, tmp_path: Path) -> None:
        assert load_notes("ghost", tmp_path / "notes.toml") == []

    def test_clear_removes_all(self, tmp_path: Path) -> None:
        nf = tmp_path / "notes.toml"
        add_note("p", "a", nf)
        add_note("p", "b", nf)
        count = clear_notes("p", nf)
        assert count == 2
        assert load_notes("p", nf) == []

    def test_clear_nonexistent_returns_zero(self, tmp_path: Path) -> None:
        assert clear_notes("ghost", tmp_path / "notes.toml") == 0

    def test_notes_isolated_per_project(self, tmp_path: Path) -> None:
        nf = tmp_path / "notes.toml"
        add_note("alpha", "alpha note", nf)
        add_note("beta", "beta note", nf)
        assert load_notes("alpha", nf)[0].text == "alpha note"
        assert load_notes("beta", nf)[0].text == "beta note"

    def test_rename_moves_notes(self, tmp_path: Path) -> None:
        nf = tmp_path / "notes.toml"
        add_note("alpha", "first note", nf)
        add_note("alpha", "second note", nf)
        rename_notes("alpha", "renamed-alpha", nf)
        assert load_notes("alpha", nf) == []
        notes = load_notes("renamed-alpha", nf)
        assert len(notes) == 2

    def test_rename_nonexistent_is_noop(self, tmp_path: Path) -> None:
        nf = tmp_path / "notes.toml"
        rename_notes("ghost", "new-name", nf)  # must not raise


class TestNotesInContext:
    def test_note_appears_in_context(self, tmp_path: Path, monkeypatch) -> None:
        import soma.notes as nm
        notes_file = tmp_path / "notes.toml"
        monkeypatch.setattr(nm, "NOTES_FILE", notes_file)
        import soma.context as ctx
        monkeypatch.setattr(ctx, "load_notes", lambda name: nm.load_notes(name, notes_file))

        root = tmp_path / "proj"
        make_repo(root, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        add_note("proj", "waiting on API keys from infra team", notes_file)

        out = generate_context("proj", root)
        assert "## Notes" in out
        assert "waiting on API keys from infra team" in out

    def test_no_notes_section_when_empty(self, tmp_path: Path, monkeypatch) -> None:
        import soma.context as ctx
        monkeypatch.setattr(ctx, "load_notes", lambda name: [])

        root = tmp_path / "proj"
        make_repo(root, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        out = generate_context("proj", root)
        assert "## Notes" not in out


class TestNotesCLI:
    def test_add_note(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        import soma.notes as nm
        notes_file = tmp_path / "notes.toml"
        monkeypatch.setattr(nm, "NOTES_FILE", notes_file)
        monkeypatch.setattr(cli_mod, "add_note", lambda p, t: nm.add_note(p, t, notes_file))
        monkeypatch.setattr(cli_mod, "load_notes", lambda p: nm.load_notes(p, notes_file))
        monkeypatch.setattr(cli_mod, "clear_notes", lambda p: nm.clear_notes(p, notes_file))

        root = make_repo(tmp_path / "alpha", [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["note", "alpha", "blocked on deploy permissions"])
        assert result.exit_code == 0, result.output
        assert "Note added" in result.output

    def test_list_notes(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        import soma.notes as nm
        notes_file = tmp_path / "notes.toml"
        monkeypatch.setattr(nm, "NOTES_FILE", notes_file)
        monkeypatch.setattr(cli_mod, "add_note", lambda p, t: nm.add_note(p, t, notes_file))
        monkeypatch.setattr(cli_mod, "load_notes", lambda p: nm.load_notes(p, notes_file))
        monkeypatch.setattr(cli_mod, "clear_notes", lambda p: nm.clear_notes(p, notes_file))

        write_registry(registry, {"alpha": tmp_path / "alpha"})
        nm.add_note("alpha", "my note", notes_file)
        result = runner.invoke(app, ["note", "alpha", "--list"])
        assert result.exit_code == 0, result.output
        assert "my note" in result.output

    def test_unknown_project_error(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["note", "ghost", "text"])
        assert result.exit_code == 1
        assert "ghost" in result.output
        assert "Traceback" not in result.output


class TestRenameCLI:
    def test_rename_succeeds(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["rename", "alpha", "beta"])
        assert result.exit_code == 0, result.output
        assert "beta" in result.output
        assert "Traceback" not in result.output

    def test_rename_unknown_old_fails(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["rename", "ghost", "new-name"])
        assert result.exit_code == 1
        assert "ghost" in result.output
        assert "Traceback" not in result.output

    def test_rename_conflict_fails(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha", "beta": tmp_path / "beta"})
        result = runner.invoke(app, ["rename", "alpha", "beta"])
        assert result.exit_code == 1
        assert "taken" in result.output.lower() or "beta" in result.output
        assert "Traceback" not in result.output


class TestBriefingCLI:
    def test_briefing_shows_active_projects(self, registry: Path, tmp_path: Path) -> None:
        root = make_repo(
            tmp_path / "alpha",
            [("a.py", "feat: init", NOW - timedelta(hours=2))],
        )
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["briefing"])
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output
        assert "Traceback" not in result.output

    def test_briefing_no_registry(self, registry: Path) -> None:
        result = runner.invoke(app, ["briefing"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_briefing_shows_note_tag(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        import soma.notes as nm
        notes_file = tmp_path / "notes.toml"
        monkeypatch.setattr(nm, "NOTES_FILE", notes_file)
        monkeypatch.setattr(cli_mod, "load_notes", lambda p: nm.load_notes(p, notes_file))

        make_repo(tmp_path / "alpha", [("a.py", "feat: init", NOW - timedelta(hours=2))])
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        nm.add_note("alpha", "blocked on deploy", notes_file)

        result = runner.invoke(app, ["briefing"])
        assert result.exit_code == 0, result.output
        assert "blocked on deploy" in result.output
