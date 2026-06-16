"""soma integrity — commit pattern integrity checker."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from soma.detect import load_registry
from soma.runtime import registry_path
from soma.signals import Severity, check_integrity

console = Console()


def integrity(
    project: str = typer.Argument(..., help="Project to run integrity checks on."),
    days: int = typer.Option(7, "--days", "-d", help="Days of recent commits to check (default: 7)."),
    warn_only: bool = typer.Option(False, "--warn-only", help="Only show warnings, skip info signals."),
) -> None:
    """Run commit pattern integrity checks on a project.

    Detects: missing co-change partners, large commits, format violations,
    and source changes without expected test coverage.

    Exit code 1 if any warnings are found (useful in CI / git hooks).
    """
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}")
        raise typer.Exit(code=1)

    root = Path(entry["root"])
    with console.status(f"Analysing [bold]{escape(project)}[/bold] (last {days}d)..."):
        signals = check_integrity(root, days=days)

    if warn_only:
        signals = [s for s in signals if s.severity == "warn"]

    if not signals:
        console.print(f"[green]✓[/green] [bold]{escape(project)}[/bold] — no integrity issues detected (last {days}d).")
        return

    warnings = [s for s in signals if s.severity == "warn"]
    infos = [s for s in signals if s.severity == "info"]

    console.print(f"\n[bold]{escape(project)}[/bold] — integrity check (last {days}d)\n")

    for s in signals:
        if s.severity == "warn":
            console.print(f"  [yellow]⚠[/yellow]  [bold]{escape(s.category)}[/bold]  {escape(s.message)}")
        else:
            console.print(f"  [dim]·[/dim]  [dim]{escape(s.category)}[/dim]  {escape(s.message)}")
        if s.detail:
            console.print(f"      [dim]{escape(s.detail)}[/dim]")

    summary_parts = []
    if warnings:
        summary_parts.append(f"[yellow]{len(warnings)} warning(s)[/yellow]")
    if infos:
        summary_parts.append(f"[dim]{len(infos)} info[/dim]")
    console.print(f"\n{', '.join(summary_parts)}")

    if warnings:
        raise typer.Exit(code=1)
