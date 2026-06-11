"""SOMA v1 CLI entry point. Commands: init, status, history, context."""
from __future__ import annotations

import os
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

from soma.config import DEFAULTS, VALID_KEYS, _BOUNDS, load_config, reset_config, set_config
from soma.context import TOKEN_CEILING, UnsafeTargetError, estimate_tokens, generate_context, generate_context_dict, write_context_file
from soma.detect import (
    PROJECTS_FILE, add_tag, find_git_roots, forget_project, get_tags,
    is_archived, load_registry, projects_by_tag, register_projects,
    remove_tag, rename_project, set_archived,
)
from soma.activity import build_activity_data, render_heatmap
from soma.filters import is_watched, should_ignore
from soma.notes import add_note, clear_notes, load_notes, rename_notes
from soma.sanitize import redact
from soma.history import collect_history, render_markdown
from soma.status import ProjectStatus, collect_statuses, get_status_safe, humanize_delta

app = typer.Typer(
    help="SOMA — System Omniscient Memory Agent (v1)",
    invoke_without_command=True,
)
console = Console()
_VERSION = "0.3.0"


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
    json_out: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Show activity status for all projects, or a deep view of one."""
    import json as _json

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


def _parse_since(value: str) -> datetime:
    """Parse '2026-06-01', '7d', '2w', '3h', 'yesterday' → UTC datetime.

    Raises ValueError for unrecognised formats.
    """
    now = datetime.now(timezone.utc)
    v = value.strip().lower()
    if v == "yesterday":
        return now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    m = re.fullmatch(r"(\d+)(d|w|h)", v)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = {"d": timedelta(days=n), "w": timedelta(weeks=n), "h": timedelta(hours=n)}[unit]
        return now - delta
    try:
        dt = datetime.strptime(value.strip(), "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    raise ValueError(
        f"Cannot parse '{value}'. Use YYYY-MM-DD, Nd (days), Nw (weeks), Nh (hours), or 'yesterday'."
    )


@app.command()
def context(
    project: Optional[str] = typer.Argument(None, help="Project name to summarize."),
    watch: bool = typer.Option(False, "--watch", help="Keep running: write CLAUDE.md into the repo and regenerate on change."),
    copy: bool = typer.Option(False, "--copy", help="Copy output to clipboard instead of printing."),
    since: Optional[str] = typer.Option(None, "--since", help="Limit activity to this date window (YYYY-MM-DD, 7d, 2w, 3h, yesterday)."),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Generate context for all projects with this tag."),
    fmt: str = typer.Option("text", "--format", "-f", help="Output format: text or json."),
) -> None:
    """Generate a compact LLM-ready context summary for a project or tag group."""
    import json as _json

    if fmt not in ("text", "json"):
        console.print(f"[red]Unknown format:[/red] {escape(fmt)}. Use 'text' or 'json'.")
        raise typer.Exit(code=1)

    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)

    since_dt: datetime | None = None
    if since:
        try:
            since_dt = _parse_since(since)
        except ValueError as exc:
            console.print(f"[red]{escape(str(exc))}[/red]")
            raise typer.Exit(code=1)

    # --group: print context for every project with that tag
    if group:
        targets = projects_by_tag(group, PROJECTS_FILE)
        if not targets:
            console.print(f"[red]No projects tagged:[/red] {escape(group)}.")
            raise typer.Exit(code=1)
        if fmt == "json":
            results = [generate_context_dict(name, Path(entry["root"]), since=since_dt) for name, entry in targets.items()]
            typer.echo(_json.dumps(results, indent=2))
            return
        parts: list[str] = []
        for name, entry in targets.items():
            parts.append(generate_context(name, Path(entry["root"]), since=since_dt))
        combined = "\n\n---\n\n".join(parts)
        if copy:
            if _copy_to_clipboard(combined):
                console.print(f"[green]Copied[/green] {len(targets)} context(s) for group [cyan]{escape(group)}[/cyan].")
            else:
                typer.echo(combined)
        else:
            typer.echo(combined)
        return

    if project is None:
        console.print("[red]Provide a project name or --group <tag>.[/red]")
        raise typer.Exit(code=1)

    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}. Run [bold]soma status[/bold] to list projects.")
        raise typer.Exit(code=1)

    root = Path(entry["root"])
    if not watch:
        if fmt == "json":
            data = generate_context_dict(project, root, since=since_dt)
            typer.echo(_json.dumps(data, indent=2))
            return
        text = generate_context(project, root, since=since_dt)
        if copy:
            if _copy_to_clipboard(text):
                console.print(f"[green]Copied[/green] context for [bold]{escape(project)}[/bold] to clipboard.")
            else:
                console.print("[yellow]Clipboard unavailable.[/yellow] Printing instead:")
                typer.echo(text)
        else:
            typer.echo(text)
        return

    console.print(
        f"Watching [bold]{escape(project)}[/bold] — regenerating "
        f"{escape(str(root / 'CLAUDE.md'))} on change (3s quiet window). Ctrl+C to stop."
    )
    last_text: Optional[str] = None
    prev_mtimes: dict[str, float] = {}
    dirty_since: float | None = None
    _DEBOUNCE_S = 3.0
    _POLL_S = 0.5
    try:
        while True:
            current_mtimes = _collect_mtimes(root)
            if current_mtimes != prev_mtimes:
                prev_mtimes = current_mtimes
                dirty_since = time.monotonic()
            if dirty_since is not None and time.monotonic() - dirty_since >= _DEBOUNCE_S:
                dirty_since = None
                try:
                    text = generate_context(project, root)
                except Exception:
                    time.sleep(_POLL_S)
                    continue
                if text != last_text:
                    target = write_context_file(root, text)
                    console.print(f"[green]updated[/green] {escape(str(target))}")
                    last_text = text
            time.sleep(_POLL_S)
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


_BASELINES_DIR = Path.home() / ".soma" / "baselines"


@app.command()
def validate(
    project: Optional[str] = typer.Argument(
        None, help="Validate one project (default: all registered projects)."
    ),
    save_baseline: bool = typer.Option(
        False, "--save-baseline", help="Save current context output as a baseline for future --compare runs."
    ),
    compare: bool = typer.Option(
        False, "--compare", help="Diff current context output against the saved baseline."
    ),
) -> None:
    """Check context quality; optionally save or diff against a baseline."""
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

    if save_baseline:
        _BASELINES_DIR.mkdir(parents=True, exist_ok=True)
        saved = 0
        for name, entry in targets.items():
            root = Path(entry["root"])
            try:
                text = generate_context(name, root)
            except Exception:
                continue
            safe = re.sub(r"[^\w\-]", "_", name)
            (_BASELINES_DIR / f"{safe}.md").write_text(text, encoding="utf-8", newline="\n")
            saved += 1
        console.print(f"[green]Saved[/green] {saved} baseline(s) to {escape(str(_BASELINES_DIR))}")
        return

    if compare:
        import difflib
        any_diff = False
        for name, entry in targets.items():
            safe = re.sub(r"[^\w\-]", "_", name)
            baseline_path = _BASELINES_DIR / f"{safe}.md"
            if not baseline_path.exists():
                console.print(f"[yellow]{escape(name)}:[/yellow] no baseline — run [dim]soma validate --save-baseline[/dim] first.")
                continue
            root = Path(entry["root"])
            try:
                current = generate_context(name, root)
            except Exception as exc:
                console.print(f"[red]{escape(name)}:[/red] error — {escape(str(exc))}")
                continue
            baseline = baseline_path.read_text(encoding="utf-8")
            diff = list(difflib.unified_diff(
                baseline.splitlines(), current.splitlines(),
                fromfile="baseline", tofile="current", lineterm=""
            ))
            if not diff:
                console.print(f"[green]{escape(name)}:[/green] no change")
            else:
                any_diff = True
                console.print(f"\n[bold yellow]{escape(name)}:[/bold yellow] {len(diff)} diff line(s)")
                for line in diff[2:]:  # skip the --- / +++ header lines
                    if line.startswith("+"):
                        console.print(f"  [green]{escape(line)}[/green]")
                    elif line.startswith("-"):
                        console.print(f"  [red]{escape(line)}[/red]")
                    else:
                        console.print(f"  [dim]{escape(line)}[/dim]")
        if any_diff:
            raise typer.Exit(code=1)
        return

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
            console.print(f"  [{n.when[:10]}] {escape(redact(n.text))}")
        return

    n = add_note(project, text)
    console.print(
        f"[green]Note added[/green] to [bold]{escape(project)}[/bold]: {escape(redact(n.text))}"
    )
    console.print("[dim]Will appear in soma context output.[/dim]")


@app.command()
def briefing(
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Filter to projects with this tag."),
    show_all: bool = typer.Option(False, "--all", help="Include archived projects."),
) -> None:
    """Morning summary: active, quiet, and dormant projects with pending notes."""
    registry = load_registry(PROJECTS_FILE)
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


@app.command()
def tag(
    project: str = typer.Argument(..., help="Project name."),
    tag_name: Optional[str] = typer.Argument(None, help="Tag to add."),
    remove: Optional[str] = typer.Option(None, "--remove", "-r", help="Tag to remove."),
    list_tags: bool = typer.Option(False, "--list", "-l", help="List current tags."),
) -> None:
    """Add, remove, or list tags on a project."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if project not in registry:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)

    if remove:
        if not remove_tag(project, remove, PROJECTS_FILE):
            console.print(f"[yellow]Tag '{escape(remove)}' not on {escape(project)}.[/yellow]")
        else:
            console.print(f"[green]Removed[/green] tag [bold]{escape(remove)}[/bold] from {escape(project)}.")
        return

    if list_tags or tag_name is None:
        tags = get_tags(project, PROJECTS_FILE)
        if tags:
            console.print(f"[bold]{escape(project)}[/bold] tags: " + ", ".join(f"[cyan]{escape(t)}[/cyan]" for t in tags))
        else:
            console.print(f"[dim]{escape(project)} has no tags.[/dim]")
        return

    add_tag(project, tag_name, PROJECTS_FILE)
    console.print(f"[green]Tagged[/green] [bold]{escape(project)}[/bold] → [cyan]{escape(tag_name)}[/cyan].")


@app.command()
def archive(
    project: str = typer.Argument(..., help="Project to archive."),
) -> None:
    """Archive a project — hidden from soma briefing unless --all."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if project not in registry:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)
    set_archived(project, True, PROJECTS_FILE)
    console.print(f"[dim]Archived[/dim] [bold]{escape(project)}[/bold]. Hidden from briefing (use [dim]soma briefing --all[/dim] to show).")


@app.command()
def unarchive(
    project: str = typer.Argument(..., help="Project to restore."),
) -> None:
    """Restore an archived project to active tier."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    if project not in registry:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)
    set_archived(project, False, PROJECTS_FILE)
    console.print(f"[green]Restored[/green] [bold]{escape(project)}[/bold] to active tier.")


@app.command()
def diff(
    project: str = typer.Argument(..., help="Project to diff against its saved baseline."),
) -> None:
    """Show what changed in a project's context since the last saved baseline."""
    import difflib as _dl

    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)

    safe = re.sub(r"[^\w\-]", "_", project)
    baseline_path = _BASELINES_DIR / f"{safe}.md"
    if not baseline_path.exists():
        console.print(
            f"[yellow]No baseline for[/yellow] [bold]{escape(project)}[/bold]. "
            f"Run [dim]soma validate {escape(project)} --save-baseline[/dim] first."
        )
        raise typer.Exit(code=1)

    root = Path(entry["root"])
    try:
        current = generate_context(project, root)
    except Exception as exc:
        console.print(f"[red]Error generating context:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1)

    baseline = baseline_path.read_text(encoding="utf-8")
    lines = list(_dl.unified_diff(
        baseline.splitlines(), current.splitlines(),
        fromfile="baseline", tofile="current", lineterm="",
    ))
    if not lines:
        console.print(f"[green]{escape(project)}:[/green] no change since baseline.")
        return

    console.print(f"\n[bold yellow]{escape(project)}[/bold yellow] — {len(lines)} diff line(s)\n")
    for line in lines[2:]:  # skip --- / +++ headers
        if line.startswith("+"):
            console.print(f"  [green]{escape(line)}[/green]")
        elif line.startswith("-"):
            console.print(f"  [red]{escape(line)}[/red]")
        else:
            console.print(f"  [dim]{escape(line)}[/dim]")
    raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """Check registry integrity, stale roots, config bounds, and git availability."""
    import shutil

    issues: list[str] = []
    ok: list[str] = []

    # git binary available
    if shutil.which("git"):
        ok.append("git binary found")
    else:
        issues.append("git binary not found — soma needs git on PATH")

    # config bounds
    cfg = load_config()
    for key, (lo, hi) in _BOUNDS.items():
        val = cfg.get(key, DEFAULTS[key])
        if lo <= val <= hi:
            ok.append(f"config {key}={val} (in bounds {lo}–{hi})")
        else:
            issues.append(f"config {key}={val} out of bounds [{lo}, {hi}]")

    # registry integrity
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        ok.append("registry empty (run soma init to populate)")
    else:
        stale = []
        non_git = []
        for name, entry in registry.items():
            root = Path(entry.get("root", ""))
            if not root.exists():
                stale.append(name)
            elif not (root / ".git").exists():
                non_git.append(name)
        ok.append(f"{len(registry)} projects registered")
        if stale:
            issues.append(f"stale roots (directory missing): {', '.join(stale)}")
        else:
            ok.append("all registered roots exist")
        if non_git:
            issues.append(f"non-git roots: {', '.join(non_git)}")
        else:
            ok.append("all roots are git repos")

    for msg in ok:
        console.print(f"  [green]✓[/green] {msg}")
    for msg in issues:
        console.print(f"  [red]✗[/red] {msg}")

    if issues:
        console.print(f"\n[red]{len(issues)} issue(s) found.[/red]")
        raise typer.Exit(code=1)
    console.print(f"\n[green]All checks passed ({len(ok)} checks).[/green]")


_HOOK_CONTENT = """\
#!/bin/sh
# soma post-commit hook — auto-regenerates CLAUDE.md
soma context {project}
"""

hook_app = typer.Typer(help="Manage soma git hooks.")
app.add_typer(hook_app, name="hook")


@hook_app.command("install")
def hook_install(
    project: str = typer.Argument(..., help="Project to install hook for."),
) -> None:
    """Write a post-commit hook that regenerates context after every commit."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)

    hook_dir = Path(entry["root"]) / ".git" / "hooks"
    if not hook_dir.exists():
        console.print(f"[red]No .git/hooks directory in {escape(entry['root'])}[/red]")
        raise typer.Exit(code=1)

    hook_path = hook_dir / "post-commit"
    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8")
        if "soma context" not in existing:
            console.print(
                f"[yellow]Existing post-commit hook not from soma.[/yellow] "
                f"Edit {escape(str(hook_path))} manually to add: soma context {escape(project)}"
            )
            raise typer.Exit(code=1)

    hook_path.write_text(_HOOK_CONTENT.format(project=project), encoding="utf-8", newline="\n")
    try:
        hook_path.chmod(0o755)
    except OSError:
        pass  # Windows — chmod no-op, git will still run it
    console.print(
        f"[green]Hook installed[/green] → {escape(str(hook_path))}\n"
        f"  After every [bold]git commit[/bold] in [bold]{escape(project)}[/bold], "
        f"CLAUDE.md regenerates automatically."
    )


@hook_app.command("remove")
def hook_remove(
    project: str = typer.Argument(..., help="Project to remove hook from."),
) -> None:
    """Remove the soma post-commit hook from a project."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)

    hook_path = Path(entry["root"]) / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        console.print(f"[dim]No post-commit hook at {escape(str(hook_path))}.[/dim]")
        return

    existing = hook_path.read_text(encoding="utf-8")
    if "soma context" not in existing:
        console.print(
            f"[yellow]Hook at {escape(str(hook_path))} was not installed by soma — leaving it.[/yellow]"
        )
        raise typer.Exit(code=1)

    hook_path.unlink()
    console.print(f"[green]Removed[/green] soma hook from [bold]{escape(project)}[/bold].")


@app.command()
def activity(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to include (default: 30)."),
    show_all: bool = typer.Option(False, "--all", help="Include archived projects."),
) -> None:
    """ASCII activity heatmap — commit frequency across all projects."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)

    if days < 1 or days > 365:
        console.print("[red]--days must be between 1 and 365.[/red]")
        raise typer.Exit(code=1)

    visible = {
        n: e for n, e in registry.items()
        if show_all or not e.get("archived", False)
    }
    if not visible:
        console.print("[dim]No projects to show.[/dim]")
        raise typer.Exit(code=1)

    with console.status(f"Fetching activity for {len(visible)} project(s)..."):
        rows, date_range = build_activity_data(visible, days=days)

    typer.echo(render_heatmap(rows, date_range))


def _collect_mtimes(root: Path, max_depth: int = 3) -> dict[str, float]:
    """Return {abs_path: mtime} for watched files under root (for debounce)."""
    result: dict[str, float] = {}
    _mtime_walk(str(root), root, 0, max_depth, result)
    return result


def _mtime_walk(
    directory: str, root: Path, depth: int, max_depth: int, result: dict[str, float]
) -> None:
    if depth > max_depth:
        return
    try:
        with os.scandir(directory) as it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        if not should_ignore(e.name):
                            _mtime_walk(e.path, root, depth + 1, max_depth, result)
                    elif is_watched(e.name):
                        result[e.path] = e.stat(follow_symlinks=False).st_mtime
                except (OSError, ValueError):
                    continue
    except OSError:
        pass


def _status_to_dict(s: ProjectStatus) -> dict:
    return {
        "name": s.name,
        "branch": s.branch,
        "last_active": s.last_active.isoformat() if s.last_active else None,
        "commits_7d": s.commits_7d,
        "files_changed_7d": s.files_changed_7d,
        "recent_commits": [
            {"message": c.message, "when": c.when.isoformat()} for c in s.recent_commits
        ],
        "warning": s.warning,
    }


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


@app.command()
def tui() -> None:
    """Launch the interactive TUI dashboard (textual)."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    try:
        from soma.tui import run_tui  # noqa: PLC0415
    except ImportError:
        console.print("[red]textual not installed.[/red] Run: pip install 'soma-cli[tui]'")
        raise typer.Exit(code=1)
    run_tui(registry)


mcp_app = typer.Typer(help="Manage the SOMA MCP server for Claude Desktop / Cursor.")
app.add_typer(mcp_app, name="mcp")

_CLAUDE_DESKTOP_CONFIG = {
    "Darwin": Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
    "Windows": Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json",
    "Linux": Path.home() / ".config" / "Claude" / "claude_desktop_config.json",
}


def _config_path() -> Path:
    import platform
    system = platform.system()
    return _CLAUDE_DESKTOP_CONFIG.get(system, _CLAUDE_DESKTOP_CONFIG["Linux"])


@mcp_app.command("start")
def mcp_start() -> None:
    """Start the SOMA MCP server (stdio transport — Claude Desktop spawns this)."""
    try:
        from soma.mcp import mcp as _mcp  # noqa: PLC0415
    except ImportError:
        console.print("[red]fastmcp not installed.[/red] Run: pip install 'soma-cli[mcp]'")
        raise typer.Exit(code=1)
    _mcp.run()


@mcp_app.command("install")
def mcp_install(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print config change without writing."),
) -> None:
    """Register soma MCP server in Claude Desktop config."""
    import json as _json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import sys  # noqa: PLC0415

    soma_bin = shutil.which("soma") or sys.executable.replace("python", "soma")
    server_entry = {
        "command": soma_bin,
        "args": ["mcp", "start"],
    }

    cfg_path = _config_path()
    if dry_run:
        console.print(f"[dim]Config path:[/dim] {escape(str(cfg_path))}")
        console.print("[dim]Would add:[/dim]")
        console.print(_json.dumps({"mcpServers": {"soma": server_entry}}, indent=2))
        return

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {}
    if cfg_path.exists():
        try:
            config = _json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            config = {}

    config.setdefault("mcpServers", {})["soma"] = server_entry
    cfg_path.write_text(_json.dumps(config, indent=2), encoding="utf-8")
    console.print(f"[green]Installed[/green] soma MCP server → {escape(str(cfg_path))}")
    console.print("Restart Claude Desktop to activate.")


@mcp_app.command("uninstall")
def mcp_uninstall() -> None:
    """Remove soma from Claude Desktop MCP config."""
    import json as _json  # noqa: PLC0415

    cfg_path = _config_path()
    if not cfg_path.exists():
        console.print("[dim]Claude Desktop config not found — nothing to remove.[/dim]")
        return

    try:
        config = _json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        console.print("[red]Could not parse config file.[/red]")
        raise typer.Exit(code=1)

    servers = config.get("mcpServers", {})
    if "soma" not in servers:
        console.print("[dim]soma not found in MCP config.[/dim]")
        return

    del servers["soma"]
    config["mcpServers"] = servers
    cfg_path.write_text(_json.dumps(config, indent=2), encoding="utf-8")
    console.print(f"[green]Removed[/green] soma from {escape(str(cfg_path))}")


if __name__ == "__main__":
    app()
