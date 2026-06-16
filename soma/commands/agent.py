"""SOMA agent commands: init, sync.

soma agent init <project>  — generate a CLAUDE.md-style agent ruleset from git
soma agent sync <project>  — refresh ruleset if project has drifted since last run
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape

from soma.detect import load_registry
from soma.filters import should_ignore
from soma.runtime import registry_path
from soma.sanitize import redact
from soma.status import humanize_delta

console = Console()

agent_app = typer.Typer(help="Generate and sync agent rulesets for your projects.")

# Where generated rulesets are stored
_AGENTS_DIR = Path.home() / ".soma" / "agents"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _project_description(root: Path) -> str:
    """Best-effort one-line description from README / pyproject / package.json."""
    # pyproject.toml description field
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
            m = re.search(r'description\s*=\s*"([^"]+)"', text)
            if m:
                return m.group(1).strip()
        except OSError:
            pass

    # package.json description field
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            if isinstance(data.get("description"), str) and data["description"]:
                return data["description"].strip()
        except (OSError, json.JSONDecodeError):
            pass

    # README.md — first non-empty, non-heading line
    for readme in ("README.md", "README.rst", "README"):
        p = root / readme
        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip().lstrip("#").strip()
                    if line and not line.startswith("!["): # skip image lines
                        return line[:120]
            except OSError:
                pass

    return "(no description found)"

def _file_frequencies(repo, limit: int = 10) -> list[tuple[str, int]]:
    """Top N files by commit touch count, noise-filtered."""
    try:
        raw = repo.git.log("--name-only", "--pretty=format:")
    except Exception:
        return []
    counts: Counter = Counter()
    for line in raw.splitlines():
        line = line.strip()
        if line and not should_ignore(line):
            counts[line] += 1
    return counts.most_common(limit)

def _top_copairs(repo, limit: int = 6) -> list[tuple[str, str, int]]:
    """Top co-changed file pairs (file_a, file_b, count)."""
    try:
        raw = repo.git.log("--name-only", "--pretty=format:---COMMIT---")
    except Exception:
        return []

    commits: list[set[str]] = []
    current: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if line == "---COMMIT---":
            if current:
                commits.append(current)
            current = set()
        elif line and not should_ignore(line):
            current.add(line)
    if current:
        commits.append(current)

    pair_counts: Counter = Counter()
    for commit in commits:
        files = sorted(commit)
        for i, a in enumerate(files):
            for b in files[i + 1:]:
                pair_counts[(a, b)] += 1

    return [(a, b, n) for (a, b), n in pair_counts.most_common(limit) if n >= 2]

def _recent_commits(repo, days: int = 14) -> list[str]:
    try:
        raw = repo.git.log(f"--since={days}.days.ago", "--pretty=format:%s")
        return [redact(line.strip()) for line in raw.splitlines() if line.strip()][:8]
    except Exception:
        return []

def _generate_ruleset(project: str, root: Path) -> str:
    """Build the AGENT.md content from git + filesystem. No LLM, no network."""
    from git import Repo  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    try:
        repo = Repo(root)
        branch = repo.active_branch.name
        freq = _file_frequencies(repo)
        copairs = _top_copairs(repo)
        recent = _recent_commits(repo)
    except Exception:
        branch, freq, copairs, recent = "unknown", [], [], []

    description = _project_description(root)

    lines = [
        f"# {project} — SOMA Agent Ruleset",
        f"<!-- Generated {date_str} by SOMA | run `soma agent sync {project}` to refresh -->",
        "",
        "## What this project is",
        description,
        "",
        f"## Branch & status",
        f"**Branch:** `{branch}`",
        "",
    ]

    if freq:
        lines += ["## Key files (by commit frequency)", ""]
        for path, count in freq[:8]:
            lines.append(f"- `{path}` — edited {count}x")
        lines.append("")

    if copairs:
        lines += ["## Co-change pairs (edit one → check the other)", ""]
        for a, b, n in copairs:
            lines.append(f"- `{a}` ↔ `{b}` ({n} times)")
        lines.append("")

    if recent:
        lines += [f"## Recent focus (last 14d)", ""]
        for msg in recent:
            lines.append(f"- {msg}")
        lines.append("")

    lines += [
        "## Do not edit (generated / noise)",
        "- `dist/`, `build/`, `__pycache__/`, `node_modules/`, `*.pyc`",
        "- Lock files: `poetry.lock`, `package-lock.json`, `Cargo.lock`",
        "",
        "---",
        f"*soma-cli {date_str} | local-first, no LLM, no network*",
    ]

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# soma agent init
# ---------------------------------------------------------------------------

@agent_app.command("init")
def agent_init(
    project: str = typer.Argument(..., help="Project name to generate ruleset for."),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Write ruleset to this path instead of ~/.soma/agents/<project>.md",
    ),
    print_only: bool = typer.Option(
        False, "--print", help="Print to stdout only; do not save to file."
    ),
) -> None:
    """Generate a CLAUDE.md-style agent ruleset for a project from git history.

    The ruleset captures: project description, key files, co-change coupling,
    recent focus, and noise-filter rules. Paste it into any agent session.

    Saved to ~/.soma/agents/<project>.md by default.
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
    with console.status(f"Building agent ruleset for [bold]{escape(project)}[/bold]..."):
        ruleset = _generate_ruleset(project, root)

    if print_only:
        typer.echo(ruleset)
        return

    dest = output or (_AGENTS_DIR / f"{project}.md")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(ruleset, encoding="utf-8")

    typer.echo(ruleset)
    console.print(f"\n[dim]Saved to {dest}[/dim]")

# ---------------------------------------------------------------------------
# soma agent sync
# ---------------------------------------------------------------------------

@agent_app.command("sync")
def agent_sync(
    project: str = typer.Argument(..., help="Project name to sync ruleset for."),
    force: bool = typer.Option(False, "--force", "-f", help="Regenerate even if up to date."),
    threshold: int = typer.Option(
        5, "--threshold", "-t",
        help="Regenerate if this many new commits since last sync (default: 5).",
    ),
) -> None:
    """Refresh the agent ruleset if the project has drifted since last sync.

    Checks how many commits happened since the ruleset was last generated.
    Regenerates automatically when the threshold is exceeded.
    """
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo
    from git.exc import GitCommandError

    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}")
        raise typer.Exit(code=1)

    dest = _AGENTS_DIR / f"{project}.md"

    if not dest.exists():
        console.print(f"[yellow]No ruleset found.[/yellow] Generating now...")
        _run_init(project, entry, dest)
        return

    # Count commits since last sync
    last_sync = datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc)
    root = Path(entry["root"])

    try:
        repo = Repo(root)
        since_str = last_sync.strftime("%Y-%m-%dT%H:%M:%S")
        raw = repo.git.log(f"--since={since_str}", "--pretty=format:%h")
        new_commits = len([l for l in raw.splitlines() if l.strip()])
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError):
        console.print(f"[red]Cannot read git history for '{escape(project)}'.[/red]")
        raise typer.Exit(code=1)

    if not force and new_commits < threshold:
        console.print(
            f"[green]{escape(project)}[/green] — ruleset is fresh "
            f"([dim]{new_commits} commit(s) since last sync, threshold {threshold}[/dim])"
        )
        console.print(f"[dim]Last synced: {humanize_delta(last_sync)}[/dim]")
        console.print(f"[dim]Use --force to regenerate anyway.[/dim]")
        return

    console.print(
        f"[yellow]{escape(project)}[/yellow] — {new_commits} new commit(s) since last sync. Regenerating..."
    )
    _run_init(project, entry, dest)

def _run_init(project: str, entry: dict, dest: Path) -> None:
    root = Path(entry["root"])
    with console.status(f"Building agent ruleset for [bold]{escape(project)}[/bold]..."):
        ruleset = _generate_ruleset(project, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(ruleset, encoding="utf-8")
    typer.echo(ruleset)
    console.print(f"\n[green]Saved[/green] → {dest}")
