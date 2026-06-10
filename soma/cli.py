"""SOMA v1 CLI entry point. Commands: init, status, history, context."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from soma.detect import PROJECTS_FILE, find_git_roots, load_registry, register_projects
from soma.status import ProjectStatus, collect_statuses, get_status_safe, humanize_delta

app = typer.Typer(help="SOMA — System Omniscient Memory Agent (v1)")
console = Console()


@app.callback()
def main() -> None:
    """Keep typer in subcommand mode."""


@app.command()
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
    console.print(f"Registry: {PROJECTS_FILE}")


@app.command()
def status(
    project: Optional[str] = typer.Argument(
        None, help="Project name for a deep view (default: all projects)."
    ),
) -> None:
    """Show activity status for all projects, or a deep view of one."""
    registry = load_registry(PROJECTS_FILE)
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
        _print_deep_view(get_status_safe(project, Path(entry["root"])))
        return

    statuses = collect_statuses(registry)
    table = Table(title=f"SOMA — {len(statuses)} project(s)")
    table.add_column("Project", style="bold")
    table.add_column("Last Active")
    table.add_column("Branch")
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


if __name__ == "__main__":
    app()
