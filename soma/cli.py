"""SOMA v1 CLI entry point. Commands: init, status, history, context."""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from datetime import datetime, timedelta, timezone

from soma.config import DEFAULTS, VALID_KEYS, load_config, reset_config, set_config
from soma.context import TOKEN_CEILING, UnsafeTargetError, estimate_tokens, generate_context, write_context_file
from soma.detect import PROJECTS_FILE, find_git_roots, forget_project, load_registry, register_projects, rename_project
from soma.notes import add_note, clear_notes, load_notes, rename_notes
from soma.history import collect_history, render_markdown
from soma.status import ProjectStatus, collect_statuses, get_status_safe, humanize_delta

app = typer.Typer(
    help="SOMA — System Omniscient Memory Agent (v1)",
    invoke_without_command=True,
)
console = Console()
_VERSION = "0.1.1"


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit.", is_eager=True),
    update: bool = typer.Option(False, "--update", help="Upgrade soma-cli via pip and exit.", is_eager=True),
    uninstall: bool = typer.Option(False, "--uninstall", help="Uninstall soma-cli and exit.", is_eager=True),
) -> None:
    """Your repos already remember everything. Now they can tell your AI."""
    if version:
        typer.echo(f"soma-cli {_VERSION}")
        raise typer.Exit()
    if update:
        console.print(f"Upgrading [bold]soma-cli[/bold] (current: {_VERSION})...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "soma-cli"],
            capture_output=False,
        )
        if result.returncode != 0:
            console.print("[red]Upgrade failed.[/red] Is soma-cli on PyPI? Try: pip install --upgrade soma-cli")
            raise typer.Exit(code=1)
        raise typer.Exit()
    if uninstall:
        typer.confirm("Uninstall soma-cli?", abort=True)
        purge = typer.confirm("Also delete ~/.soma/ registry data?", default=False)
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "soma-cli"])
        if purge:
            import shutil
            soma_dir = Path.home() / ".soma"
            if soma_dir.exists():
                shutil.rmtree(soma_dir)
                console.print(f"[dim]Removed {soma_dir}[/dim]")
        console.print("[green]soma-cli uninstalled.[/green]")
        raise typer.Exit()
    if ctx.invoked_subcommand is not None:
        return
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("[bold]SOMA[/bold] — no projects registered yet.")
        console.print("  Run [bold cyan]soma init[/bold cyan] to scan your home directory.")
        return
    statuses = collect_statuses(registry)
    active = [s for s in statuses if s.commits_7d > 0][:5]
    console.print(f"[bold]SOMA[/bold] — {len(registry)} project(s) registered\n")
    if active:
        console.print("[bold]Recently active:[/bold]")
        for s in active:
            console.print(
                f"  [cyan]{escape(s.name):<28}[/cyan] "
                f"{humanize_delta(s.last_active):<12} "
                f"[dim]{escape(s.branch)}[/dim]"
            )
    console.print(
        f"\n[dim]soma status[/dim]          all projects"
        f"\n[dim]soma context <project>[/dim]  generate LLM summary"
        f"\n[dim]soma history[/dim]         last 7 days of activity"
    )


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


@app.command()
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
    registry = load_registry(PROJECTS_FILE)
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


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    import platform
    plat = platform.system()
    try:
        if plat == "Windows":
            subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True, capture_output=True)
        elif plat == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, capture_output=True)
        else:
            # Linux: try xclip then xsel
            try:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True, capture_output=True)
            except FileNotFoundError:
                subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode("utf-8"), check=True, capture_output=True)
        return True
    except Exception:
        return False


@app.command()
def context(
    project: str = typer.Argument(..., help="Project name to summarize."),
    watch: bool = typer.Option(
        False,
        "--watch",
        help="Keep running: write CLAUDE.md into the repo and regenerate on change.",
    ),
    copy: bool = typer.Option(
        False,
        "--copy",
        help="Copy output to clipboard instead of printing.",
    ),
) -> None:
    """Generate a compact LLM-ready context summary for a project."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(
            f"[red]Unknown project:[/red] {escape(project)}. "
            "Run [bold]soma status[/bold] to list projects."
        )
        raise typer.Exit(code=1)
    root = Path(entry["root"])
    if not watch:
        text = generate_context(project, root)
        if copy:
            if _copy_to_clipboard(text):
                console.print(f"[green]Copied[/green] context for [bold]{escape(project)}[/bold] to clipboard.")
            else:
                console.print("[yellow]Clipboard unavailable.[/yellow] Printing instead:")
                typer.echo(text)
        else:
            # Plain echo, not rich: the output is markdown meant to be copy-pasted.
            typer.echo(text)
        return

    console.print(
        f"Watching [bold]{escape(project)}[/bold] — regenerating "
        f"{escape(str(root / 'CLAUDE.md'))} on change. Ctrl+C to stop."
    )
    last: Optional[str] = None
    try:
        while True:
            text = generate_context(project, root)
            if text != last:
                target = write_context_file(root, text)
                console.print(f"[green]updated[/green] {escape(str(target))}")
                last = text
            time.sleep(5)
    except UnsafeTargetError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        console.print("Stopped.")


_REQUIRED_SECTIONS = (
    "## Recent work",
    "## Files in motion",
    "## Possible blockers",
    "## Suggested focus",
)
_TOKEN_FLOOR = 350


@app.command()
def validate(
    project: Optional[str] = typer.Argument(
        None, help="Validate one project (default: all registered projects)."
    ),
) -> None:
    """Check context quality for all projects: token budget, format, no secrets."""
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
        targets = {project: entry}
    else:
        targets = registry

    table = Table(title="SOMA — Context validation")
    table.add_column("Project", style="bold", max_width=28, no_wrap=True)
    table.add_column("Tokens", justify="right")
    table.add_column("Format")
    table.add_column("Secrets")
    table.add_column("Status")

    cfg = load_config()
    effective_ceiling = cfg["token_ceiling"]

    any_fail = False
    for name, entry in targets.items():
        root = Path(entry["root"])
        try:
            text = generate_context(name, root)
        except Exception as exc:
            table.add_row(escape(name), "—", "—", "—", f"[red]ERROR: {escape(str(exc))}[/red]")
            any_fail = True
            continue

        tokens = estimate_tokens(text)
        missing = [s for s in _REQUIRED_SECTIONS if s not in text]
        fmt_ok = not missing
        secrets_clean = not any(
            pat in text
            for pat in ("api_key=", "secret=", "Bearer ", "sk-", "ghp_")
        )

        token_str = str(tokens)
        if tokens > effective_ceiling:
            token_str = f"[red]{tokens}[/red]"
            any_fail = True
        elif tokens < _TOKEN_FLOOR:
            token_str = f"[yellow]{tokens}[/yellow]"

        fmt_str = "[green]OK[/green]" if fmt_ok else f"[red]missing: {', '.join(missing)}[/red]"
        sec_str = "[green]clean[/green]" if secrets_clean else "[red]LEAK[/red]"

        if not fmt_ok or not secrets_clean or tokens > effective_ceiling:
            status_str = "[red]FAIL[/red]"
            any_fail = True
        elif tokens < _TOKEN_FLOOR:
            status_str = "[yellow]WARN (low tokens)[/yellow]"
        else:
            status_str = "[green]OK[/green]"

        table.add_row(escape(name), token_str, fmt_str, sec_str, status_str)

    console.print(table)
    if any_fail:
        raise typer.Exit(code=1)


@app.command()
def note(
    project: str = typer.Argument(..., help="Project name."),
    text: Optional[str] = typer.Argument(None, help="Note text to add."),
    list_notes: bool = typer.Option(False, "--list", "-l", help="List existing notes."),
    clear: bool = typer.Option(False, "--clear", help="Remove all notes for this project."),
) -> None:
    """Add a manual annotation to a project (surfaced in soma context)."""
    registry = load_registry(PROJECTS_FILE)
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
            console.print(f"  [{n.when[:10]}] {escape(n.text)}")
        return

    n = add_note(project, text)
    console.print(
        f"[green]Note added[/green] to [bold]{escape(project)}[/bold]: {escape(n.text)}"
    )
    console.print("[dim]Will appear in soma context output.[/dim]")


@app.command()
def briefing() -> None:
    """Morning summary: active, quiet, and dormant projects with pending notes."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)

    now = datetime.now(timezone.utc)
    statuses = collect_statuses(registry)

    active, quiet, dormant = [], [], []
    for s in statuses:
        age = (now - s.last_active).days if s.last_active else 9999
        if s.commits_7d > 0:
            active.append(s)
        elif age <= 30:
            quiet.append(s)
        else:
            dormant.append(s)

    date_str = now.strftime("%Y-%m-%d %H:%M")
    console.print(f"\n[bold]SOMA Briefing[/bold] — {date_str}\n")

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
            console.print(f"    [yellow]↳ {escape(notes[0].text)}[/yellow]")

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


@app.command()
def export(
    project: Optional[str] = typer.Argument(
        None, help="Project to export (default: all registered projects)."
    ),
    dir: Optional[Path] = typer.Option(
        None, "--dir", "-d", help="Output directory (default: current directory)."
    ),
) -> None:
    """Export context summaries to markdown files."""
    registry = load_registry(PROJECTS_FILE)
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


@app.command()
def rename(
    old: str = typer.Argument(..., help="Current project name."),
    new: str = typer.Argument(..., help="New project name."),
) -> None:
    """Rename a project in the SOMA registry."""
    registry = load_registry(PROJECTS_FILE)
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
    rename_project(old, new, PROJECTS_FILE)
    rename_notes(old, new)
    console.print(f"[green]Renamed[/green] [bold]{escape(old)}[/bold] → [bold]{escape(new)}[/bold].")


@app.command()
def forget(
    project: str = typer.Argument(..., help="Project name to remove from registry."),
) -> None:
    """Remove a project from the SOMA registry (does not delete files)."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if project not in registry:
        console.print(
            f"[red]Unknown project:[/red] {escape(project)}. "
            "Run [bold]soma status[/bold] to list projects."
        )
        raise typer.Exit(code=1)
    forget_project(project, PROJECTS_FILE)
    console.print(f"[green]Removed[/green] [bold]{escape(project)}[/bold] from registry.")
    console.print("[dim]Files on disk untouched. Re-run soma init to re-register.[/dim]")


config_app = typer.Typer(help="Manage SOMA configuration.", invoke_without_command=True)
app.add_typer(config_app, name="config")


@config_app.callback()
def config_default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _config_list()


@config_app.command("list")
def config_list() -> None:
    """Show all config keys with current and default values."""
    _config_list()


def _config_list() -> None:
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
    try:
        set_config(key, int_val)
    except ValueError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(code=1)
    console.print(
        f"[green]Set[/green] [bold]{escape(key)}[/bold] = {int_val} "
        f"[dim](was {DEFAULTS[key]})[/dim]"
    )


@config_app.command("reset")
def config_reset(
    key: str = typer.Argument(..., help="Config key to reset to default."),
) -> None:
    """Reset a config key to its default value."""
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


@app.command()
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
    registry = load_registry(PROJECTS_FILE)
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
        except Exception:
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
