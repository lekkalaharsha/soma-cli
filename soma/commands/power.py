"""SOMA power user commands: activity, diff, doctor, tui, drift, predict, verify, why, team."""
from __future__ import annotations

import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from soma.runtime import registry_path
from soma.detect import load_registry
from soma.activity import build_activity_data, render_heatmap
from soma.context import generate_context
from soma.config import load_config, _BOUNDS, DEFAULTS

console = Console()

# Path to track when each project context was last loaded
_SESSIONS_FILE = Path.home() / ".soma" / "sessions.toml"


def _load_sessions() -> dict:
    try:
        import tomllib  # noqa: PLC0415
        return tomllib.loads(_SESSIONS_FILE.read_text(encoding="utf-8")) if _SESSIONS_FILE.exists() else {}
    except Exception:
        return {}


def _save_session(project: str) -> None:
    """Record that context was loaded for project right now."""
    try:
        import tomllib  # noqa: PLC0415
        sessions = _load_sessions()
        sessions[project] = datetime.now(timezone.utc).isoformat()
        lines = [f'{k} = "{v}"' for k, v in sessions.items()]
        _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SESSIONS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass  # session tracking is best-effort, never crash for it


def _last_seen(project: str) -> datetime | None:
    sessions = _load_sessions()
    raw = sessions.get(project)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def activity(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to include (default: 30)."),
    show_all: bool = typer.Option(False, "--all", help="Include archived projects."),
) -> None:
    """ASCII activity heatmap — commit frequency across all projects."""
    registry = load_registry(registry_path())
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


def diff(
    project: str = typer.Argument(..., help="Project to diff against its saved baseline."),
) -> None:
    """Show what changed in a project's context since the last saved baseline."""
    import difflib as _dl
    from soma.cli import _BASELINES_DIR

    registry = load_registry(registry_path())
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
    except Exception as exc:  # git/OS/parse; surface to user and exit
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


def doctor() -> None:
    """Check registry integrity, stale roots, config bounds, and git availability."""
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
    registry = load_registry(registry_path())
    if not registry:
        ok.append("registry empty (run soma init to populate)")
    else:
        stale = []
        non_git = []
        for name, entry in registry.items():
            root = Path(entry.get("root", ""))
            if not root.exists():
                stale.appe