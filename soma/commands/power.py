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


def tui() -> None:
    """Launch the interactive TUI dashboard (textual)."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    try:
        from soma.tui import run_tui  # noqa: PLC0415
    except ImportError:
        console.print("[red]textual not installed.[/red] Run: pip install 'soma-cli[tui]'")
        raise typer.Exit(code=1)
    run_tui(registry)


# ---------------------------------------------------------------------------
# soma drift
# ---------------------------------------------------------------------------

def drift(
    project: str = typer.Argument(..., help="Project name to check for drift."),
    since: Optional[str] = typer.Option(None, "--since", "-s", help="Time reference: '2h', '1d', 'yesterday', 'YYYY-MM-DD'. Defaults to last time you ran soma context."),
) -> None:
    """Show what changed in a project since your last session.

    Use this to catch up after a break: new commits, files touched, branch.
    """
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo  # noqa: PLC0415
    from git.exc import GitCommandError, GitCommandNotFound  # noqa: PLC0415
    from soma.cli_helpers import _parse_since  # noqa: PLC0415
    from soma.sanitize import redact  # noqa: PLC0415
    from soma.status import humanize_delta  # noqa: PLC0415

    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}")
        raise typer.Exit(code=1)

    # Resolve the since timestamp
    if since:
        try:
            since_dt = _parse_since(since)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1)
    else:
        since_dt = _last_seen(project)
        if since_dt is None:
            since_dt = datetime.now(timezone.utc) - timedelta(hours=24)
            console.print("[dim]No previous session found — showing last 24h.[/dim]\n")
        else:
            console.print(f"[dim]Since last context load: {humanize_delta(since_dt)}[/dim]\n")

    root = Path(entry["root"])
    try:
        repo = Repo(root)
        since_str = since_dt.strftime("%Y-%m-%dT%H:%M:%S")
        log = repo.git.log(f"--since={since_str}", "--pretty=format:%h %s", "--name-only")
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError, GitCommandNotFound):
        console.print(f"[red]Cannot read git history for '{escape(project)}'.[/red]")
        raise typer.Exit(code=1)

    if not log.strip():
        console.print(f"[green]{escape(project)}[/green] — no changes since then. You're caught up.")
        return

    # Parse commits and files
    commits: list[str] = []
    files: set[str] = set()
    current_commit: str | None = None
    for line in log.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^[0-9a-f]{7} ", line):
            current_commit = redact(line)
            commits.append(current_commit)
        elif current_commit:
            files.add(line)

    console.print(f"[bold cyan]{escape(project)}[/bold cyan] — drift since {humanize_delta(since_dt)}\n")
    console.print(f"  [bold]{len(commits)}[/bold] new commit(s), [bold]{len(files)}[/bold] file(s) touched\n")

    console.print("[bold]Commits:[/bold]")
    for c in commits[:10]:
        console.print(f"  [green]+[/green] {escape(c)}")

    if files:
        console.print(f"\n[bold]Files touched:[/bold]")
        for f in sorted(files)[:15]:
            console.print(f"  [dim]·[/dim] {escape(f)}")

    # Record this as a session
    _save_session(project)


# ---------------------------------------------------------------------------
# soma predict
# ---------------------------------------------------------------------------

def predict(
    project: str = typer.Argument(..., help="Project name."),
    file: str = typer.Argument(..., help="File path to predict co-changes for."),
    min_count: int = typer.Option(2, "--min", help="Minimum co-change count to show (default: 2)."),
) -> None:
    """Predict which files will also need changes based on historical co-change patterns.

    Uses git history to find files that always change together with <file>.
    Helps agents understand implicit coupling before touching code.
    """
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo  # noqa: PLC0415
    from git.exc import GitCommandError, GitCommandNotFound  # noqa: PLC0415

    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}")
        raise typer.Exit(code=1)

    root = Path(entry["root"])
    try:
        repo = Repo(root)
        log = repo.git.log("-n", "1000", "--pretty=format:---COMMIT---", "--name-only")
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError, GitCommandNotFound):
        console.print(f"[red]Cannot read git history for '{escape(project)}'.[/red]")
        raise typer.Exit(code=1)

    # Group files per commit
    commits_with_file: list[set[str]] = []
    current: set[str] = set()
    for line in log.splitlines():
        line = line.strip()
        if line == "---COMMIT---":
            if current:
                commits_with_file.append(current)
            current = set()
        elif line:
            current.add(line)
    if current:
        commits_with_file.append(current)

    # Find commits that touched our target file
    target_commits = [c for c in commits_with_file if file in c]
    total = len(target_commits)

    if total == 0:
        console.print(f"[yellow]No commits found touching '{escape(file)}'.[/yellow]")
        raise typer.Exit(code=1)

    # Count co-occurrences
    co_counts: Counter = Counter()
    for commit in target_commits:
        for f in commit:
            if f != file:
                co_counts[f] += 1

    results = [(f, count) for f, count in co_counts.most_common(15) if count >= min_count]

    console.print(f"\n[bold cyan]soma predict[/bold cyan] — {escape(project)} / {escape(file)}\n")
    console.print(f"Found [bold]{total}[/bold] commit(s) touching this file.\n")

    if not results:
        console.print("[dim]No strong co-change patterns found (try --min 1).[/dim]")
        return

    console.print("[bold]If you edit this file, history says you'll likely also need:[/bold]\n")
    table = Table(show_header=True, header_style="bold")
    table.add_column("File", style="cyan")
    table.add_column("Co-changed", justify="right")
    table.add_column("Out of", justify="right")
    table.add_column("Confidence", justify="right")

    for f, count in results:
        pct = int(count / total * 100)
        confidence = "always" if pct >= 90 else "usually" if pct >= 60 else "sometimes"
        style = "green" if pct >= 90 else "yellow" if pct >= 60 else "dim"
        table.add_row(escape(f), str(count), str(total), f"[{style}]{confidence} ({pct}%)[/{style}]")

    console.print(table)


# ---------------------------------------------------------------------------
# soma verify
# ---------------------------------------------------------------------------

def verify(
    project: str = typer.Argument(..., help="Project name."),
    claim: str = typer.Argument(..., help="Claim to verify against git, e.g. 'auth was changed last week'."),
) -> None:
    """Fact-check a claim about a project against its git history.

    Uses simple keyword matching (matches filenames, tokens, and time ranges)
    against the git log to verify claims. Note: this command does NOT perform
    semantic natural language understanding (NLU) or make any LLM calls.
    """
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo  # noqa: PLC0415
    from git.exc import GitCommandError, GitCommandNotFound  # noqa: PLC0415
    from soma.status import humanize_delta  # noqa: PLC0415

    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}")
        raise typer.Exit(code=1)

    root = Path(entry["root"])
    try:
        repo = Repo(root)
    except (InvalidGitRepositoryError, NoSuchPathError):
        console.print(f"[red]Cannot open repo for '{escape(project)}'.[/red]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold cyan]soma verify[/bold cyan] — checking claim against git\n")
    console.print(f'[dim]Claim:[/dim] "{escape(claim)}"\n')

    findings: list[tuple[str, bool, str]] = []  # (subject, verified, detail)

    # Extract file/path tokens from claim (words containing . or /)
    file_tokens = re.findall(r"[\w\-]+(?:[./][\w\-]+)+", claim)
    for token in file_tokens[:5]:
        try:
            log = repo.git.log("-n", "1000", "--pretty=format:%ci %s", "--", token)
            if log:
                first_line = log.splitlines()[0]
                findings.append((f"'{token}' exists in git history", True, first_line[:80]))
            else:
                findings.append((f"'{token}' found in git history", False, "No commits touch this path"))
        except GitCommandError:
            pass

    # Extract time references
    time_patterns = [
        (r"(\d+)\s*day[s]?\s*ago", lambda m: timedelta(days=int(m.group(1)))),
        (r"(\d+)\s*week[s]?\s*ago", lambda m: timedelta(weeks=int(m.group(1)))),
        (r"(\d+)\s*hour[s]?\s*ago", lambda m: timedelta(hours=int(m.group(1)))),
        (r"last\s*week", lambda m: timedelta(weeks=1)),
        (r"yesterday", lambda m: timedelta(days=1)),
    ]
    now = datetime.now(timezone.utc)
    for pattern, delta_fn in time_patterns:
        m = re.search(pattern, claim, re.IGNORECASE)
        if m:
            claimed_dt = now - delta_fn(m)
            # Check if any commit happened around that time (±50% window)
            window = delta_fn(m) * 0.5
            since = (claimed_dt - window).strftime("%Y-%m-%dT%H:%M:%S")
            until = (claimed_dt + window).strftime("%Y-%m-%dT%H:%M:%S")
            try:
                log = repo.git.log("-n", "1000", f"--after={since}", f"--before={until}", "--pretty=format:%s", "--")
                if log:
                    findings.append((f"Activity around {m.group(0)}", True, log.splitlines()[0][:80]))
                else:
                    # Find the actual nearest commit
                    nearest = repo.git.log("-1", "--pretty=format:%ci %s")
                    findings.append((f"Activity around {m.group(0)}", False, f"No commits then. Nearest: {nearest[:60]}"))
            except GitCommandError:
                pass
            break

    # Always show actual latest commit as ground truth
    try:
        latest = repo.git.log("-1", "--pretty=format:%ci — %s")
        findings.append(("Latest commit (ground truth)", True, latest))
    except GitCommandError:
        pass

    if not findings:
        console.print("[yellow]Could not extract verifiable facts from claim.[/yellow]")
        console.print("[dim]Tip: include file names or time references like '3 days ago'.[/dim]")
        return

    for subject, verified, detail in findings:
        icon = "[green]✓[/green]" if verified else "[red]✗[/red]"
        console.print(f"  {icon} {escape(subject)}")
        console.print(f"      [dim]{escape(detail)}[/dim]\n")


# ---------------------------------------------------------------------------
# soma why
# ---------------------------------------------------------------------------

def why(
    project: str = typer.Argument(..., help="Project name."),
    file: str = typer.Argument(..., help="File path to explain (relative to repo root)."),
) -> None:
    """Explain why a file exists and how it evolved, from git history alone.

    Derives developer themes and purpose strictly by checking word frequencies
    in commit messages and git log follow-history. This command does NOT perform
    semantic natural language understanding (NLU) or make any LLM calls.
    """
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo  # noqa: PLC0415
    from git.exc import GitCommandError, GitCommandNotFound  # noqa: PLC0415
    from soma.sanitize import redact  # noqa: PLC0415
    from soma.status import humanize_delta  # noqa: PLC0415

    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}")
        raise typer.Exit(code=1)

    root = Path(entry["root"])
    try:
        repo = Repo(root)
        log = repo.git.log("-n", "1000", "--follow", "--pretty=format:%ci\t%an\t%s", "--", file)
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError, GitCommandNotFound):
        console.print(f"[red]Cannot read git history for '{escape(project)}'.[/red]")
        raise typer.Exit(code=1)

    if not log.strip():
        console.print(f"[yellow]No git history found for '{escape(file)}'.[/yellow]")
        raise typer.Exit(code=1)

    entries = []
    for line in log.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            entries.append({"date": parts[0].strip(), "author": parts[1].strip(), "msg": redact(parts[2].strip())})

    created = entries[-1]
    latest = entries[0]
    authors = Counter(e["author"] for e in entries)

    # Derive purpose from commit message keywords (simple frequency)
    all_words = " ".join(e["msg"] for e in entries).lower()
    # Strip conventional commit prefixes
    all_words = re.sub(r"\b(feat|fix|chore|refactor|test|docs|style|perf)\b[:(]?\s*", "", all_words)
    word_freq = Counter(w for w in re.findall(r"[a-z]{4,}", all_words) if w not in {
        "that", "this", "with", "from", "have", "been", "were", "will", "into", "also", "when", "then"
    })
    top_words = [w for w, _ in word_freq.most_common(5)]

    console.print(f"\n[bold cyan]soma why[/bold cyan] — {escape(project)} / {escape(file)}\n")
    console.print(f"  [bold]Created:[/bold]     {created['date'][:10]} by {escape(created['author'])}")
    console.print(f"  [bold]First commit:[/bold] {escape(created['msg'])}")
    console.print(f"  [bold]Last changed:[/bold] {latest['date'][:10]} — {escape(latest['msg'])}")
    console.print(f"  [bold]Total commits:[/bold] {len(entries)}")
    console.print(f"  [bold]Authors:[/bold]     {', '.join(f'{a} ({n}x)' for a, n in authors.most_common(3))}")
    if top_words:
        console.print(f"  [bold]Key themes:[/bold]  {', '.join(top_words)}")

    console.print(f"\n[bold]Commit history:[/bold]")
    for e in entries[:8]:
        console.print(f"  [dim]{e['date'][:10]}[/dim]  {escape(e['msg'])}")
    if len(entries) > 8:
        console.print(f"  [dim]... and {len(entries) - 8} more[/dim]")


# ---------------------------------------------------------------------------
# soma team
# ---------------------------------------------------------------------------

def team(
    project: str = typer.Argument(..., help="Project name."),
    days: int = typer.Option(30, "--days", "-d", help="Days of history to scan (default: 30)."),
) -> None:
    """Show per-author commit activity on a shared repo.

    No cloud, no server — reads your local git clone.
    Useful for understanding team activity before making changes.
    """
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo  # noqa: PLC0415
    from git.exc import GitCommandError, GitCommandNotFound  # noqa: PLC0415
    from soma.sanitize import redact  # noqa: PLC0415
    from soma.status import humanize_delta  # noqa: PLC0415

    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}")
        raise typer.Exit(code=1)

    root = Path(entry["root"])
    try:
        repo = Repo(root)
        log = repo.git.log(
            f"--since={days}.days.ago",
            "--pretty=format:%an\t%ae\t%ci\t%s",
        )
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError, GitCommandNotFound):
        console.print(f"[red]Cannot read git history for '{escape(project)}'.[/red]")
        raise typer.Exit(code=1)

    if not log.strip():
        console.print(f"[dim]No commits in the last {days} day(s) for '{escape(project)}'.[/dim]")
        return

    # Group by author
    author_data: dict[str, dict] = {}
    for line in log.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        name, email, date_str, msg = parts
        name = name.strip()
        if name not in author_data:
            author_data[name] = {"commits": 0, "last": date_str.strip(), "recent": []}
        author_data[name]["commits"] += 1
        if len(author_data[name]["recent"]) < 3:
            author_data[name]["recent"].append(redact(msg.strip()))

    console.print(f"\n[bold cyan]soma team[/bold cyan] — {escape(project)} (last {days}d)\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Author", style="cyan")
    table.add_column("Commits", justify="right")
    table.add_column("Last commit")
    table.add_column("Recent work", style="dim")

    for name, data in sorted(author_data.items(), key=lambda x: -x[1]["commits"]):
        table.add_row(
            escape(name),
            str(data["commits"]),
            data["last"][:10],
            escape(data["recent"][0][:50]) if data["recent"] else "",
        )

    console.print(table)
    console.print(f"\n[dim]{sum(d['commits'] for d in author_data.values())} total commits, {len(author_data)} contributor(s)[/dim]")
