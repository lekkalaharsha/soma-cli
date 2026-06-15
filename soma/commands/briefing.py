"""SOMA briefing and notes commands: briefing, note."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape

from soma.runtime import registry_path
from soma.detect import load_registry
from soma.sanitize import redact
from soma.status import ProjectStatus, collect_statuses, humanize_delta

console = Console()


def note(
    project: str = typer.Argument(..., help="Project name."),
    text: Optional[str] = typer.Argument(None, help="Note text to add."),
    list_notes: bool = typer.Option(False, "--list", "-l", help="List existing notes."),
    clear: bool = typer.Option(False, "--clear", help="Remove all notes for this project."),
) -> None:
    """Add a manual annotation to a project (surfaced in soma context)."""
    from soma.cli import add_note, clear_notes, load_notes

    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if project not in registry:
        console.print(
            f"[red]Unknown project:[/red] {escape(project)}. "
            "Run [bold]soma status[/bold] to list projects."
        )
        raise typer.Exit(code=1)

    if clear:
        count = clear_notes(project)
        console.print(f"[green]Cleared[/green] {count} note(s) for [bold]{escape(project)}[/bold].")
        return

    if list_notes or text is None:
        notes = load_notes(project)
        if not notes:
            console.print(f"No notes for [bold]{escape(project)}[/bold].")
            return
        console.print(f"[bold]Notes for {escape(project)}:[/bold]")
        for n in notes:
            console.print(f"  [{n.when[:10]}] {escape(redact(n.text))}")
        return

    n = add_note(project, text)
    console.print(
        f"[green]Note added[/green] to [bold]{escape(project)}[/bold]: {escape(redact(n.text))}"
    )
    console.print("[dim]Will appear in soma context output.[/dim]")


def briefing(
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Filter to projects with this tag."),
    show_all: bool = typer.Option(False, "--all", help="Include archived projects."),
) -> None:
    """Morning summary: active, quiet, and dormant projects with pending notes."""
    from soma.cli import load_notes

    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)

    now = datetime.now(timezone.utc)

    # Filter by group tag and archived state before collecting statuses
    visible = {
        n: e for n, e in registry.items()
        if (show_all or not e.get("archived", False))
        and (group is None or group in e.get("tags", []))
    }
    if not visible:
        label = f"group [cyan]{escape(group)}[/cyan]" if group else "registry"
        console.print(f"[dim]No projects in {label}.[/dim]")
        raise typer.Exit(code=1)

    statuses = collect_statuses(visible)

    active, quiet, dormant = [], [], []
    for s in statuses:
        age = (now - s.last_active).days if s.last_active else 9999
        if s.commits_7d > 0:
            active.append(s)
        elif age <= 30:
            quiet.append(s)
        else:
            dormant.append(s)

    group_label = f" [{escape(group)}]" if group else ""
    date_str = now.strftime("%Y-%m-%d %H:%M")
    console.print(f"\n[bold]SOMA Briefing{group_label}[/bold] — {date_str}\n")

    def _row(s: ProjectStatus) -> None:
        notes = load_notes(s.name)
        note_tag = f" [yellow][{len(notes)} note(s)][/yellow]" if notes else ""
        age_str = humanize_delta(s.last_active, now)
        commits_str = f"{s.commits_7d}c" if s.commits_7d else "no commits"
        console.print(
            f"  [bold cyan]{escape(s.name[:28]):<28}[/bold cyan] "
            f"[dim]{escape(s.branch):<16}[/dim] "
            f"{age_str:<12} {commits_str}{note_tag}"
        )
        if notes:
            console.print(f"    [yellow]↳ {escape(redact(notes[0].text))}[/yellow]")

    if active:
        console.print(f"[green]Active[/green] ({len(active)})")
        for s in active:
            _row(s)
        console.print()

    if quiet:
        console.print(f"[yellow]Quiet[/yellow] — no commits this week ({len(quiet)})")
        for s in quiet[:5]:
            _row(s)
        if len(quiet) > 5:
            console.print(f"  [dim]...and {len(quiet) - 5} more[/dim]")
        console.print()

    if dormant:
        console.print(f"[dim]Dormant >30d ({len(dormant)})[/dim]")
        for s in dormant[:3]:
            _row(s)
        if len(dormant) > 3:
            console.print(f"  [dim]...and {len(dormant) - 3} more[/dim]")
        console.print()

    total_notes = sum(1 for s in statuses if load_notes(s.name))
    if total_notes:
        console.print(f"[yellow]{total_notes} project(s) have pending notes.[/yellow] "
                      "Run [dim]soma note <project> --list[/dim] to review.")
