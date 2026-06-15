"""SOMA context-related commands: context, validate."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from soma.runtime import registry_path
from soma.detect import load_registry, projects_by_tag
from soma.cli_helpers import _collect_mtimes, _parse_since
from soma.context import (
    UnsafeTargetError, estimate_tokens, generate_context,
    generate_context_dict, write_context_file,
)

console = Console()

_REQUIRED_SECTIONS = (
    "## Recent work",
    "## Files in motion",
    "## Possible blockers",
    "## Suggested focus",
)
_TOKEN_FLOOR = 350


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
    from soma.cli import _copy_to_clipboard

    if fmt not in ("text", "json"):
        console.print(f"[red]Unknown format:[/red] {escape(fmt)}. Use 'text' or 'json'.")
        raise typer.Exit(code=1)

    registry = load_registry(registry_path())
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
        targets = projects_by_tag(group, registry_path())
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
                except Exception:  # git/OS/parse; retry on next poll cycle
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
    from soma.cli import _BASELINES_DIR, load_config

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
            except Exception:  # git/OS/parse; skip repo and continue saving others
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
            except Exception as exc:  # git/OS/parse; report and skip
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
        except Exception as exc:  # git/OS/parse; record row error and continue
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
