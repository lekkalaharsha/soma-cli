"""SOMA v1 CLI entry point. Commands: init, status, history, context."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from soma.detect import PROJECTS_FILE, find_git_roots, register_projects

app = typer.Typer(help="SOMA — System Omniscient Memory Agent (v1)")
console = Console()


@app.callback()
def main() -> None:
    """Keep typer in subcommand mode while init is the only command."""


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


if __name__ == "__main__":
    app()
