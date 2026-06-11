"""SOMA TUI dashboard — `soma tui`.

A human-facing live terminal UI built on textual. No daemon: data is read
on launch and on demand (refresh keypress). Three panels:

    left   — projects table (↑↓ to navigate)
    top-r  — context summary for the selected project
    bot-r  — notes for the selected project

Keybindings: ↑↓ navigate · r refresh · n add note · c copy context · q quit
"""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Label, Static

from soma.context import generate_context
from soma.detect import PROJECTS_FILE, load_registry
from soma.notes import add_note, load_notes
from soma.status import ProjectStatus, collect_statuses, humanize_delta


class NoteModal(ModalScreen[str | None]):
    """Single-line input overlay for adding a note to the selected project."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, project: str) -> None:
        super().__init__()
        self._project = project

    def compose(self) -> ComposeResult:
        with Vertical(id="note-dialog"):
            yield Label(f"Add note to [b]{self._project}[/b]:")
            yield Input(placeholder="Note text — Enter to save, Esc to cancel", id="note-input")

    def on_mount(self) -> None:
        self.query_one("#note-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.dismiss(text or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SomaTUI(App):
    """Interactive dashboard over registered SOMA projects."""

    TITLE = "SOMA"
    SUB_TITLE = "project memory dashboard"

    CSS = """
    Screen { layout: horizontal; }

    #projects {
        width: 38%;
        border: round $primary;
    }

    #right { width: 62%; }

    #context-scroll {
        height: 1fr;
        border: round $secondary;
    }

    #notes-panel {
        height: 12;
        border: round $warning;
        padding: 0 1;
    }

    #note-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }

    DataTable { height: 1fr; }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("n", "add_note", "Add note"),
        ("c", "copy_context", "Copy context"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        registry: dict[str, dict] | None = None,
        projects_file: Path = PROJECTS_FILE,
    ) -> None:
        super().__init__()
        self._projects_file = projects_file
        self._projects = registry if registry is not None else load_registry(projects_file)
        self._statuses: list[ProjectStatus] = []
        self.current_project: str | None = None

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        yield Header()
        table: DataTable = DataTable(id="projects", cursor_type="row", zebra_stripes=True)
        yield table
        with Vertical(id="right"):
            with VerticalScroll(id="context-scroll"):
                yield Static("", id="context-body")
            yield Static("", id="notes-panel")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#projects", DataTable)
        table.add_columns("Project", "Branch", "Last active", "7d")
        self._load_rows()

    # ------------------------------------------------------------------ data
    def _load_rows(self) -> None:
        """(Re)populate the projects table from current registry."""
        table = self.query_one("#projects", DataTable)
        table.clear()
        if not self._projects:
            self.query_one("#context-body", Static).update(
                "No projects registered.\n\nRun [b]soma init[/b] first."
            )
            self.query_one("#notes-panel", Static).update("")
            self.current_project = None
            return

        self._statuses = collect_statuses(self._projects)
        for s in self._statuses:
            table.add_row(
                s.name[:30],
                s.branch[:16],
                humanize_delta(s.last_active),
                str(s.commits_7d),
                key=s.name,
            )
        if self._statuses:
            table.focus()
            # First row highlights automatically; force-render its detail.
            self._show_project(self._statuses[0].name)

    def _show_project(self, name: str) -> None:
        self.current_project = name
        entry = self._projects.get(name)
        body = self.query_one("#context-body", Static)
        if entry is None:
            body.update(f"Unknown project: {name}")
            return
        try:
            text = generate_context(name, Path(entry["root"]))
        except Exception as exc:  # never crash the UI on a bad repo
            text = f"[red]Error generating context for {name}:[/red]\n{exc}"
        body.update(text)
        self._show_notes(name)

    def _show_notes(self, name: str) -> None:
        notes = load_notes(name)
        panel = self.query_one("#notes-panel", Static)
        if not notes:
            panel.update("[dim]No notes. Press [b]n[/b] to add one.[/dim]")
            return
        lines = ["[b]Notes[/b]"]
        for note in notes[:5]:
            lines.append(f"• {note.text}")
        panel.update("\n".join(lines))

    # ------------------------------------------------------------------ events
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None and event.row_key.value:
            self._show_project(event.row_key.value)

    # ------------------------------------------------------------------ actions
    def action_refresh(self) -> None:
        self._projects = load_registry(self._projects_file)
        self._load_rows()
        self.notify("Refreshed.", timeout=2)

    def action_add_note(self) -> None:
        if not self.current_project:
            return
        project = self.current_project

        def _save(text: str | None) -> None:
            if text:
                add_note(project, text)
                if self.current_project == project:
                    self._show_notes(project)
                self.notify(f"Note added to {project}.", timeout=2)

        self.push_screen(NoteModal(project), _save)

    def action_copy_context(self) -> None:
        if not self.current_project:
            return
        entry = self._projects.get(self.current_project)
        if entry is None:
            return
        try:
            text = generate_context(self.current_project, Path(entry["root"]))
        except Exception:
            self.notify("Could not generate context.", severity="error", timeout=3)
            return
        from soma.cli import _copy_to_clipboard  # lazy — avoids circular import

        if _copy_to_clipboard(text):
            self.notify(f"Copied context for {self.current_project}.", timeout=2)
        else:
            self.notify("Clipboard unavailable.", severity="warning", timeout=3)


def run_tui(registry: dict[str, dict] | None = None) -> None:
    """Entry point used by the `soma tui` CLI command."""
    SomaTUI(registry=registry).run()
