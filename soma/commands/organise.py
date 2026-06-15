"""SOMA project organisation commands: tag, archive, unarchive, export, search, config."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from soma.runtime import registry_path
from soma.detect import (
    load_registry, projects_by_tag, add_tag, remove_tag,
    get_tags, set_archived,
)
from soma.config import DEFAULTS, VALID_KEYS
from soma.context import generate_context

console = Console()


def tag(
    project: str = typer.Argument(..., help="Project name."),
    tag_name: Optional[str] = typer.Argument(None, help="Tag to add."),
    remove: Optional[str] = typer.Option(None, "--remove", "-r", help="Tag to remove."),
    list_tags: bool = typer.Option(False, "--list", "-l", help="List current tags."),
) -> None:
    """Add, remove, or list tags on a project."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if project not in registry:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)

    if remove:
        if not remove_tag(project, remove, registry_path()):
            console.print(f"[yellow]Tag '{escape(remove)}' not on {escape(project)}.[/yellow]")
        else:
            console.print(f"[green]Removed[/green] tag [bold]{escape(remove)}[/bold] from {escape(project)}.")
        return

    if list_tags or tag_name is None:
        tags = get_tags(project, registry_path())
        if tags:
            console.print(f"[bold]{escape(project)}[/bold] tags: " + ", ".join(f"[cyan]{escape(t)}[/cyan]" for t in tags))
        else:
            console.print(f"[dim]{escape(project)} has no tags.[/dim]")
        return

    add_tag(project, tag_name, registry_path())
    console.print(f"[green]Tagged[/green] [bold]{escape(project)}[/bold] → [cyan]{escape(tag_name)}[/cyan].")


def archive(
    project: str = typer.Argument(..., help="Project to archive."),
) -> None:
    """Archive a project — hidden from soma briefing unless --all."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if project not in registry:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)
    set_archived(project, True, registry_path())
    console.print(f"[dim]Archived[/dim] [bold]{escape(project)}[/bold]. Hidden from briefing (use [dim]soma briefing --all[/dim] to show).")


def unarchive(
    project: str = typer.Argument(..., help="Project to restore."),
) -> None:
    """Restore an archived project to active tier."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if project not in registry:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)
    set_archived(project, False, registry_path())
    console.print(f"[green]Restored[/green] [bold]{escape(project)}[/bold] to active tier.")


def export(
    project: Optional[str] = typer.Argument(
        None, help="Project to export (default: all registered projects)."
    ),
    dir: Optional[Path] = typer.Option(
        None, "--dir", "-d", help="Output directory (default: current directory)."
    ),
) -> None:
    """Export context summaries to markdown files."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)

    if project is not None:
        if project not in registry:
            console.print(
                f"[red]Unknown project:[/red] {escape(project)}. "
                "Run [bold]soma status[/bold] to list projects."
            )
            raise typer.Exit(code=1)
        targets = {project: registry[project]}
    else:
        targets = registry

    out_dir = (dir or Path.cwd()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for name, entry in targets.items():
        root = Path(entry["root"])
        text = generate_context(name, root)
        safe_name = re.sub(r"[^\w\-]", "_", name)
        dest = out_dir / f"{safe_name}_context.md"
        dest.write_text(text, encoding="utf-8", newline="\n")
        console.print(f"[green]wrote[/green] {escape(str(dest))}")
        written += 1

    console.print(f"\n{written} file(s) exported to {escape(str(out_dir))}")


def search(
    keyword: str = typer.Argument(..., help="Keyword to search across all project contexts."),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Limit search to one project."
    ),
    case_sensitive: bool = typer.Option(
        False, "--case-sensitive", "-c", help="Case-sensitive match (default: case-insensitive)."
    ),
) -> None:
    """Search a keyword across all project context summaries."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)

    if project is not None:
        if project not in registry:
            console.print(
                f"[red]Unknown project:[/red] {escape(project)}. "
                "Run [bold]soma status[/bold] to list projects."
            )
            raise typer.Exit(code=1)
        targets = {project: registry[project]}
    else:
        targets = registry

    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(keyword), flags)

    total_hits = 0
    for name, entry in targets.items():
        root = Path(entry["root"])
        try:
            text = generate_context(name, root)
        except Exception:  # git/OS/parse; skip repo from search results
            continue
        hits = [line for line in text.splitlines() if pattern.search(line)]
        if not hits:
            continue
        console.print(f"\n[bold cyan]{escape(name)}[/bold cyan]")
        for line in hits:
            highlighted = pattern.sub(
                lambda m: f"[bold yellow]{escape(m.group())}[/bold yellow]",
                escape(line),
            )
            console.print(f"  {highlighted}")
        total_hits += len(hits)

    if total_hits == 0:
        console.print(f"[dim]No matches for[/dim] [bold]{escape(keyword)}[/bold].")
        raise typer.Exit(code=1)
    else:
        console.print(f"\n[dim]{total_hits} match(es) across {len(targets)} project(s).[/dim]")


config_app = typer.Typer(help="Manage SOMA configuration.", invoke_without_command=True)


@config_app.callback()
def config_default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _config_list()


@config_app.command("list")
def config_list() -> None:
    """Show all config keys with current and default values."""
    _config_list()


def _config_list() -> None:
    from soma.cli import load_config

    cfg = load_config()
    table = Table(title="SOMA — Configuration")
    table.add_column("Key", style="bold")
    table.add_column("Current", justify="right")
    table.add_column("Default", justify="right", style="dim")
    for key in VALID_KEYS:
        current = cfg[key]
        default = DEFAULTS[key]
        val_str = str(current)
        if current != default:
            val_str = f"[cyan]{current}[/cyan]"
        table.add_row(key, val_str, str(default))
    console.print(table)


@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Config key to read."),
) -> None:
    """Print the current value of a config key."""
    from soma.cli import load_config

    if key not in VALID_KEYS:
        console.print(
            f"[red]Unknown key:[/red] {escape(key)}. "
            f"Valid: {', '.join(VALID_KEYS)}"
        )
        raise typer.Exit(code=1)
    cfg = load_config()
    typer.echo(cfg[key])


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key to set."),
    value: str = typer.Argument(..., help="New value (integer)."),
) -> None:
    """Set a config key to a new value."""
    from soma.cli import set_config

    if key not in VALID_KEYS:
        console.print(
            f"[red]Unknown key:[/red] {escape(key)}. "
            f"Valid: {', '.join(VALID_KEYS)}"
        )
        raise typer.Exit(code=1)
    try:
        int_val = int(value)
    except ValueError:
        console.print(f"[red]Value must be an integer, got:[/red] {escape(value)}")
        raise typer.Exit(code=1)
    from soma.cli import load_config as _load_cfg  # noqa: PLC0415
    prev_val = _load_cfg()[key]  # read current persisted value BEFORE overwriting
    try:
        set_config(key, int_val)
    except ValueError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(code=1)
    console.print(
        f"[green]Set[/green] [bold]{escape(key)}[/bold] = {int_val} "
        f"[dim](was {prev_val})[/dim]"
    )


@config_app.command("reset")
def config_reset(
    key: str = typer.Argument(..., help="Config key to reset to default."),
) -> None:
    """Reset a config key to its default value."""
    from soma.cli import reset_config

    if key not in VALID_KEYS:
        console.print(
            f"[red]Unknown key:[/red] {escape(key)}. "
            f"Valid: {', '.join(VALID_KEYS)}"
        )
        raise typer.Exit(code=1)
    removed = reset_config(key)
    if removed:
        console.print(
            f"[green]Reset[/green] [bold]{escape(key)}[/bold] → default ({DEFAULTS[key]})"
        )
    else:
        console.print(
            f"[dim]{escape(key)}[/dim] already at default ({DEFAULTS[key]})"
        )
