"""SOMA core commands: init, status, history, forget, rename."""
from __future__ import annotations

import sys
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from soma.detect import (
    find_git_roots, forget_project, load_registry,
    register_projects, rename_project,
)
from soma.notes import rename_notes
from soma.runtime import registry_path
from soma.status import ProjectStatus, collect_statuses, get_status_safe, humanize_delta
from soma.history import collect_history, render_markdown

console = Console()


def init(
    base: Optional[Path] = typer.Option(
        None, "--base", help="Directory to scan (default: your home directory)."
    ),
) -> None:
    """Scan ~/ for git repos and register projects."""
    scan_base = (base or Path.home()).resolve()
    if not scan_base.is_dir():
        console.print(f"[red]Not a directory:[/red] {scan_base}")
        raise typer.Exit(code=1)

    with console.status(f"Scanning {scan_base} for git repos..."):
        roots = find_git_roots(scan_base)
    new, known = register_projects(roots)

    if not roots:
        console.print(f"No git repos found under {scan_base} (max depth 4).")
        raise typer.Exit()

    table = Table(title=f"SOMA — {len(roots)} project(s) detected")
    table.add_column("Name", style="bold")
    table.add_column("Root")
    table.add_column("Status")
    for project in new:
        table.add_row(project.name, project.root, "[green]new[/green]")
    for project in known:
        table.add_row(project.name, project.root, "[dim]already registered[/dim]")
    console.print(table)
    console.print(f"Registry: {registry_path()}")


def status(
    project: Optional[str] = typer.Argument(
        None, help="Project name for a deep view (default: all projects)."
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Show activity status for all projects, or a deep view of one."""
    import json as _json
    from soma.cli_helpers import _status_to_dict

    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)

    if project is not None:
        entry = registry.get(project)
        if entry is None:
            console.print(
                f"[red]Unknown project:[/red] {escape(project)}. "
                "Run [bold]soma status[/bold] to list projects."
            )
            raise typer.Exit(code=1)
        s = get_status_safe(project, Path(entry["root"]))
        if json_out:
            typer.echo(_json.dumps(_status_to_dict(s), indent=2))
            return
        _print_deep_view(s)
        return

    statuses = collect_statuses(registry)
    if json_out:
        typer.echo(_json.dumps([_status_to_dict(s) for s in statuses], indent=2))
        return

    table = Table(title=f"SOMA — {len(statuses)} project(s)")
    table.add_column("Project", style="bold", no_wrap=True, max_width=28)
    table.add_column("Last Active")
    table.add_column("Branch", no_wrap=True, max_width=22)
    table.add_column("Commits")
    table.add_column("Files (7d)")
    for s in statuses:
        table.add_row(
            escape(s.name),
            humanize_delta(s.last_active),
            escape(s.branch),
            str(s.commits_7d),
            str(len(s.files_changed_7d)),
        )
    console.print(table)
    for s in statuses:
        if s.warning:
            console.print(f"[yellow]{escape(s.name)}: {escape(s.warning)}[/yellow]")


def _print_deep_view(s: ProjectStatus) -> None:
    console.print(f"[bold]Project:[/bold]      {escape(s.name)}")
    console.print(f"[bold]Branch:[/bold]       {escape(s.branch)}")
    console.print(f"[bold]Last active:[/bold]  {humanize_delta(s.last_active)}")
    if s.recent_commits:
        last = s.recent_commits[0]
        console.print(
            f'[bold]Last commit:[/bold]  "{escape(last.message)}" '
            f"({humanize_delta(last.when)})"
        )
        console.print(f"[bold]Recent commits (last {len(s.recent_commits)}):[/bold]")
        for c in s.recent_commits:
            console.print(f"  - {escape(c.message)} ({humanize_delta(c.when)})")
    else:
        console.print("[bold]Last commit:[/bold]  — (no git history)")
    if s.files_changed_7d:
        console.print("[bold]Files changed (7d):[/bold]")
        for path in s.files_changed_7d:
            console.print(f"  - {escape(path)}")
    else:
        console.print("[bold]Files changed (7d):[/bold] none")
    if s.warning:
        console.print(f"[yellow]{escape(s.warning)}[/yellow]")


def history(
    project: Optional[str] = typer.Argument(
        None, help="Limit the log to one project."
    ),
    days: int = typer.Option(7, "--days", help="How many days back to include."),
    markdown: bool = typer.Option(
        False, "--markdown", help="Emit markdown for notes/standups."
    ),
) -> None:
    """Show a timestamped activity log per day per project."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if project is not None and project not in registry:
        console.print(
            f"[red]Unknown project:[/red] {escape(project)}. "
            "Run [bold]soma status[/bold] to list projects."
        )
        raise typer.Exit(code=1)

    day_events = collect_history(registry, days=days, project=project)
    if markdown:
        typer.echo(render_markdown(day_events))
        return
    if not day_events:
        console.print(f"No activity in the last {days} day(s).")
        return
    for day in sorted(day_events, reverse=True):
        console.print(f"[bold]{day.isoformat()}[/bold]")
        for event in day_events[day]:
            console.print(
                f"  {event.when:%H:%M}  [cyan]{escape(event.project)}[/cyan]  "
                f"{escape(event.message)}"
            )


def rename(
    old: str = typer.Argument(..., help="Current project name."),
    new: str = typer.Argument(..., help="New project name."),
) -> None:
    """Rename a project in the SOMA registry."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if old not in registry:
        console.print(
            f"[red]Unknown project:[/red] {escape(old)}. "
            "Run [bold]soma status[/bold] to list projects."
        )
        raise typer.Exit(code=1)
    if new in registry:
        console.print(
            f"[red]Name already taken:[/red] {escape(new)}. "
            "Choose a different name."
        )
        raise typer.Exit(code=1)
    rename_project(old, new, registry_path())
    rename_notes(old, new)
    console.print(f"[green]Renamed[/green] [bold]{escape(old)}[/bold] → [bold]{escape(new)}[/bold].")


def forget(
    project: str = typer.Argument(..., help="Project name to remove from registry."),
) -> None:
    """Remove a project from the SOMA registry (does not delete files)."""
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
    forget_project(project, registry_path())
    console.print(f"[green]Removed[/green] [bold]{escape(project)}[/bold] from registry.")
    console.print("[dim]Files on disk untouched. Re-run soma init to re-register.[/dim]")
