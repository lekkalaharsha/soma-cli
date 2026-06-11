"""Tests for P2.2 — SOMA TUI dashboard (textual).

Uses textual's async test harness (App.run_test + Pilot) wrapped in
asyncio.run so the suite needs no pytest-asyncio plugin.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import partial
from pathlib import Path

import pytest
from textual.widgets import DataTable, Input, Static

from conftest import NOW, make_repo, write_registry
from soma.tui import NoteModal, SomaTUI


def _run(coro_factory) -> None:
    """Run an async scenario to completion."""
    asyncio.run(coro_factory())


@pytest.fixture()
def two_projects(tmp_path: Path) -> tuple[Path, Path]:
    """A registry file with two real git repos. Returns (registry_path, tmp_path)."""
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    make_repo(alpha, [("a.py", "feat: alpha init", NOW - timedelta(hours=1))])
    make_repo(beta, [("b.py", "feat: beta init", NOW - timedelta(hours=3))])
    reg = tmp_path / "projects.toml"
    write_registry(reg, {"alpha": alpha, "beta": beta})
    return reg, tmp_path


# ---------------------------------------------------------------------------
# Table population & selection
# ---------------------------------------------------------------------------
class TestTablePopulation:
    def test_rows_match_registry(self, two_projects) -> None:
        reg, _ = two_projects

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                table = app.query_one("#projects", DataTable)
                assert table.row_count == 2

        _run(scenario)

    def test_first_project_auto_selected(self, two_projects) -> None:
        reg, _ = two_projects

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.current_project in {"alpha", "beta"}

        _run(scenario)

    def test_context_panel_shows_selected(self, two_projects) -> None:
        reg, _ = two_projects

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                body = app.query_one("#context-body", Static)
                rendered = str(body.render())
                assert app.current_project in rendered
                assert "Recent work" in rendered

        _run(scenario)

    def test_columns_present(self, two_projects) -> None:
        reg, _ = two_projects

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                table = app.query_one("#projects", DataTable)
                labels = [str(c.label) for c in table.columns.values()]
                assert labels == ["Project", "Branch", "Last active", "7d"]

        _run(scenario)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
class TestNavigation:
    def test_down_changes_selection(self, two_projects) -> None:
        reg, _ = two_projects

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                first = app.current_project
                await pilot.press("down")
                await pilot.pause()
                second = app.current_project
                assert first != second

        _run(scenario)

    def test_selection_updates_context(self, two_projects) -> None:
        reg, _ = two_projects

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("down")
                await pilot.pause()
                body = app.query_one("#context-body", Static)
                assert app.current_project in str(body.render())

        _run(scenario)


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------
class TestRefresh:
    def test_refresh_keeps_rows(self, two_projects) -> None:
        reg, _ = two_projects

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("r")
                await pilot.pause()
                table = app.query_one("#projects", DataTable)
                assert table.row_count == 2

        _run(scenario)

    def test_refresh_picks_up_new_project(self, two_projects) -> None:
        reg, tmp_path = two_projects

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                gamma = tmp_path / "gamma"
                make_repo(gamma, [("g.py", "feat: gamma", NOW - timedelta(hours=2))])
                write_registry(reg, {
                    "alpha": tmp_path / "alpha",
                    "beta": tmp_path / "beta",
                    "gamma": gamma,
                })
                await pilot.press("r")
                await pilot.pause()
                table = app.query_one("#projects", DataTable)
                assert table.row_count == 3

        _run(scenario)


# ---------------------------------------------------------------------------
# Empty registry
# ---------------------------------------------------------------------------
class TestEmptyRegistry:
    def test_empty_shows_message_no_crash(self, tmp_path: Path) -> None:
        reg = tmp_path / "empty.toml"

        async def scenario() -> None:
            app = SomaTUI(registry={}, projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                table = app.query_one("#projects", DataTable)
                assert table.row_count == 0
                body = app.query_one("#context-body", Static)
                assert "No projects registered" in str(body.render())
                assert app.current_project is None

        _run(scenario)


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
class TestNotes:
    def test_no_notes_message(self, two_projects, tmp_path: Path, monkeypatch) -> None:
        reg, _ = two_projects
        import soma.tui as tui_mod
        notes_file = tmp_path / "notes.toml"
        from soma.notes import load_notes as real_load
        monkeypatch.setattr(tui_mod, "load_notes", partial(real_load, path=notes_file))

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                panel = app.query_one("#notes-panel", Static)
                assert "No notes" in str(panel.render())

        _run(scenario)

    def test_add_note_persists(self, two_projects, tmp_path: Path, monkeypatch) -> None:
        reg, _ = two_projects
        import soma.tui as tui_mod
        from soma.notes import add_note as real_add, load_notes as real_load
        notes_file = tmp_path / "notes.toml"
        monkeypatch.setattr(tui_mod, "add_note", partial(real_add, path=notes_file))
        monkeypatch.setattr(tui_mod, "load_notes", partial(real_load, path=notes_file))

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                project = app.current_project
                await pilot.press("n")
                await pilot.pause()
                # Type into the modal input and submit
                inp = app.screen.query_one("#note-input", Input)
                inp.value = "ship the release"
                await pilot.press("enter")
                await pilot.pause()
                notes = real_load(project, path=notes_file)
                assert any(n.text == "ship the release" for n in notes)

        _run(scenario)

    def test_add_note_updates_panel(self, two_projects, tmp_path: Path, monkeypatch) -> None:
        reg, _ = two_projects
        import soma.tui as tui_mod
        from soma.notes import add_note as real_add, load_notes as real_load
        notes_file = tmp_path / "notes.toml"
        monkeypatch.setattr(tui_mod, "add_note", partial(real_add, path=notes_file))
        monkeypatch.setattr(tui_mod, "load_notes", partial(real_load, path=notes_file))

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("n")
                await pilot.pause()
                app.screen.query_one("#note-input", Input).value = "panel check"
                await pilot.press("enter")
                await pilot.pause()
                panel = app.query_one("#notes-panel", Static)
                assert "panel check" in str(panel.render())

        _run(scenario)

    def test_note_modal_cancel_adds_nothing(self, two_projects, tmp_path: Path, monkeypatch) -> None:
        reg, _ = two_projects
        import soma.tui as tui_mod
        from soma.notes import add_note as real_add, load_notes as real_load
        notes_file = tmp_path / "notes.toml"
        monkeypatch.setattr(tui_mod, "add_note", partial(real_add, path=notes_file))
        monkeypatch.setattr(tui_mod, "load_notes", partial(real_load, path=notes_file))

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                project = app.current_project
                await pilot.press("n")
                await pilot.pause()
                app.screen.query_one("#note-input", Input).value = "discard me"
                await pilot.press("escape")
                await pilot.pause()
                assert real_load(project, path=notes_file) == []

        _run(scenario)


# ---------------------------------------------------------------------------
# Copy context
# ---------------------------------------------------------------------------
class TestCopyContext:
    def test_copy_invokes_clipboard(self, two_projects, monkeypatch) -> None:
        reg, _ = two_projects
        captured: dict[str, str] = {}

        def fake_copy(text: str) -> bool:
            captured["text"] = text
            return True

        import soma.cli as cli_mod
        monkeypatch.setattr(cli_mod, "_copy_to_clipboard", fake_copy)

        async def scenario() -> None:
            app = SomaTUI(projects_file=reg)
            async with app.run_test() as pilot:
                await pilot.pause()
                project = app.current_project
                await pilot.press("c")
                await pilot.pause()
                assert "text" in captured
                assert project in captured["text"]

        _run(scenario)


# ---------------------------------------------------------------------------
# Bindings & modal
# ---------------------------------------------------------------------------
class TestBindings:
    def test_all_bindings_registered(self) -> None:
        keys = {b[0] if isinstance(b, tuple) else b.key for b in SomaTUI.BINDINGS}
        assert {"r", "n", "c", "q"} <= keys

    def test_note_modal_holds_project(self) -> None:
        modal = NoteModal("alpha")
        assert modal._project == "alpha"
