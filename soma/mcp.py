"""SOMA MCP server — exposes soma tools to Claude Desktop / Cursor.

Run with: soma mcp start
Install with: soma mcp install

No LLM calls, no network. Pure local git heuristics served over stdio.
"""
from __future__ import annotations

import json
from pathlib import Path

from git.exc import GitCommandNotFound

from fastmcp import FastMCP

from soma.commands.power import _last_seen, _save_session
from soma.context import generate_context
from soma.detect import load_registry
from soma.history import collect_history, render_markdown
from soma.notes import load_notes
from soma.runtime import registry_path
from soma.sanitize import redact
from soma.status import collect_statuses, get_status_safe, humanize_delta

mcp = FastMCP(
    name="soma",
    instructions=(
        "SOMA gives you live context from local git repos — "
        "no copy-paste needed. Call get_context before answering "
        "questions about a project's current state."
    ),
)


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------

@mcp.tool()
def list_projects(format: str = "text") -> str:
    """List all registered projects with their branch and last-active time.

    Args:
        format: Output format - "text" (default) or "json".
    """
    registry = load_registry(registry_path())
    if not registry:
        return "No projects registered. Run `soma init` first."
    statuses = collect_statuses(registry)

    if format == "json":
        return json.dumps({
            "projects": [
                {
                    "name": s.name,
                    "branch": s.branch,
                    "last_active": humanize_delta(s.last_active),
                    "commits_7d": s.commits_7d,
                }
                for s in statuses
            ]
        })

    lines = [f"{'Project':<28} {'Branch':<18} Last active"]
    lines.append("-" * 60)
    for s in statuses:
        lines.append(
            f"{s.name[:28]:<28} {s.branch[:18]:<18} {humanize_delta(s.last_active)}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# get_context
# ---------------------------------------------------------------------------

@mcp.tool()
def get_context(project: str, format: str = "text") -> str:
    """Return SOMA context summary (~500 tokens) for a named project.

    This is the primary tool. Call it before answering questions about
    what a project is, what was recently worked on, or what to do next.

    Args:
        project: Registered project name.
        format: Output format - "text" (default) or "json".
    """
    registry = load_registry(registry_path())
    if not registry:
        return "No projects registered. Run `soma init` first."
    entry = registry.get(project)
    if entry is None:
        known = ", ".join(sorted(registry.keys())[:10])
        return f"Unknown project '{project}'. Known projects: {known}"

    summary = generate_context(project, Path(entry["root"]))

    if format == "json":
        s = get_status_safe(project, Path(entry["root"]))
        return json.dumps({
            "project": project,
            "branch": s.branch,
            "last_active": humanize_delta(s.last_active),
            "commits_7d": s.commits_7d,
            "summary": summary,
        })

    return summary


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------

@mcp.tool()
def get_history(project: str | None = None, days: int = 7, format: str = "text") -> str:
    """Return commit history across all projects (or one project) for the last N days.

    Use this for questions like "what did I work on yesterday?",
    "what changed this week?", or "show me recent commits on <project>".

    Args:
        project: Filter to a single registered project name. Omit for all projects.
        days: How many days back to look (default 7).
        format: Output format - "text" (default, markdown) or "json".
    """
    registry = load_registry(registry_path())
    if not registry:
        return "No projects registered. Run `soma init` first."

    history = collect_history(registry, days=days, project=project)

    if not history:
        scope = f"'{project}'" if project else "any project"
        return f"No commits found in the last {days} day(s) for {scope}."

    if format == "json":
        result: list[dict] = []
        for day, events in sorted(history.items(), reverse=True):
            result.append({
                "date": day.isoformat(),
                "commits": [
                    {
                        "time": e.when.strftime("%H:%M"),
                        "project": e.project,
                        "message": e.message,
                    }
                    for e in events
                ],
            })
        return json.dumps({"days": result, "total_commits": sum(len(v) for v in history.values())})

    return render_markdown(history)


# ---------------------------------------------------------------------------
# get_diff
# ---------------------------------------------------------------------------

@mcp.tool()
def get_diff(project: str, days: int = 7, format: str = "text") -> str:
    """Return recent file changes with lines added/removed for a project.

    Use this for questions like "what files changed in <project>?",
    "what did we add to <project> this week?", or "show me the diff stats".

    Args:
        project: Registered project name.
        days: How many days back to look (default 7).
        format: Output format - "text" (default) or "json".
    """
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo
    from git.exc import GitCommandError

    registry = load_registry(registry_path())
    if not registry:
        return "No projects registered. Run `soma init` first."
    entry = registry.get(project)
    if entry is None:
        known = ", ".join(sorted(registry.keys())[:10])
        return f"Unknown project '{project}'. Known projects: {known}"

    root = Path(entry["root"])
    try:
        repo = Repo(root)
        raw = repo.git.log(f"--since={days}.days.ago", "--numstat", "--pretty=format:")
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError, GitCommandNotFound):
        return f"Could not read git history for '{project}'."

    file_stats: dict[str, dict[str, int]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added_str, removed_str, filepath = parts
        if not added_str.isdigit() or not removed_str.isdigit():
            continue
        filepath = redact(filepath)
        if filepath not in file_stats:
            file_stats[filepath] = {"added": 0, "removed": 0}
        file_stats[filepath]["added"] += int(added_str)
        file_stats[filepath]["removed"] += int(removed_str)

    if not file_stats:
        return f"No file changes in the last {days} day(s) for '{project}'."

    sorted_files = sorted(
        file_stats.items(),
        key=lambda kv: kv[1]["added"] + kv[1]["removed"],
        reverse=True,
    )

    if format == "json":
        return json.dumps({
            "project": project,
            "days": days,
            "files": [
                {"path": fp, "added": s["added"], "removed": s["removed"]}
                for fp, s in sorted_files
            ],
        })

    lines = [f"# {project} - file changes (last {days}d)", ""]
    lines.append(f"{'File':<50} {'+ added':>8} {'- removed':>10}")
    lines.append("-" * 70)
    for fp, s in sorted_files[:20]:
        lines.append(f"{fp[:50]:<50} {s['added']:>8} {s['removed']:>10}")
    total_added = sum(s["added"] for _, s in file_stats.items())
    total_removed = sum(s["removed"] for _, s in file_stats.items())
    lines.append("-" * 70)
    lines.append(f"{'TOTAL':<50} {total_added:>8} {total_removed:>10}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# search_projects
# ---------------------------------------------------------------------------

@mcp.tool()
def search_projects(keyword: str) -> str:
    """Search a keyword across all project context summaries.

    Returns matching lines with project names. Case-insensitive.
    """
    import re

    registry = load_registry(registry_path())
    if not registry:
        return "No projects registered."

    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    results: list[str] = []
    for name, entry in registry.items():
        try:
            text = generate_context(name, Path(entry["root"]))
        except Exception:
            continue
        hits = [line for line in text.splitlines() if pattern.search(line)]
        if hits:
            results.append(f"[{name}]")
            results.extend(f"  {line}" for line in hits[:5])

    if not results:
        return f"No matches for '{keyword}'."
    return "\n".join(results)


# ---------------------------------------------------------------------------
# get_briefing
# ---------------------------------------------------------------------------

@mcp.tool()
def get_briefing(format: str = "text") -> str:
    """Return a morning briefing - active, quiet, and dormant projects.

    Use this for broad questions like "what should I work on?" or
    "which projects have pending notes?".

    Args:
        format: Output format - "text" (default) or "json".
    """
    from datetime import datetime, timezone

    registry = load_registry(registry_path())
    if not registry:
        return "No projects registered. Run `soma init` first."

    visible = {n: e for n, e in registry.items() if not e.get("archived", False)}
    if not visible:
        return "All projects are archived."

    now = datetime.now(timezone.utc)
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

    if format == "json":
        def _proj(s):
            notes = load_notes(s.name)
            return {
                "name": s.name,
                "branch": s.branch,
                "last_active": humanize_delta(s.last_active, now),
                "commits_7d": s.commits_7d,
                "notes": len(notes),
            }
        return json.dumps({
            "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "active": [_proj(s) for s in active],
            "quiet": [_proj(s) for s in quiet],
            "dormant": [{"name": s.name, "last_active": humanize_delta(s.last_active, now)} for s in dormant],
        })

    lines: list[str] = [f"SOMA Briefing - {now.strftime('%Y-%m-%d %H:%M')} UTC", ""]
    if active:
        lines.append(f"ACTIVE ({len(active)})")
        for s in active:
            notes = load_notes(s.name)
            note_tag = f" [{len(notes)} note(s)]" if notes else ""
            lines.append(f"  {s.name} | {s.branch} | {s.commits_7d} commits this week{note_tag}")
    if quiet:
        lines.append(f"\nQUIET - no commits this week ({len(quiet)})")
        for s in quiet[:5]:
            lines.append(f"  {s.name} | {s.branch} | last active {humanize_delta(s.last_active, now)}")
    if dormant:
        lines.append(f"\nDORMANT >30d ({len(dormant)})")
        for s in dormant[:3]:
            lines.append(f"  {s.name} | last active {humanize_delta(s.last_active, now)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# get_drift
# ---------------------------------------------------------------------------

@mcp.tool()
def get_drift(project: str, since: str | None = None, format: str = "text") -> str:
    """Return what changed in a project since the last context load or a given time.

    Call this BEFORE get_context to check if context is stale.
    Use for questions like "what changed since I last looked at <project>?"

    Args:
        project: Registered project name.
        since: Optional time reference - "2h", "1d", "yesterday", "YYYY-MM-DD".
               Defaults to when context was last loaded for this project.
        format: "text" (default) or "json".
    """
    import re as _re
    from datetime import datetime, timedelta, timezone
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo
    from git.exc import GitCommandError
    from soma.cli_helpers import _parse_since

    registry = load_registry(registry_path())
    if not registry:
        return "No projects registered. Run `soma init` first."
    entry = registry.get(project)
    if entry is None:
        known = ", ".join(sorted(registry.keys())[:10])
        return f"Unknown project '{project}'. Known projects: {known}"

    if since:
        try:
            since_dt = _parse_since(since)
        except ValueError as e:
            return str(e)
    else:
        since_dt = _last_seen(project)
        if since_dt is None:
            since_dt = datetime.now(timezone.utc) - timedelta(hours=24)

    root = Path(entry["root"])
    try:
        repo = Repo(root)
        since_str = since_dt.strftime("%Y-%m-%dT%H:%M:%S")
        log = repo.git.log(f"--since={since_str}", "--pretty=format:%h %s", "--name-only")
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError, GitCommandNotFound):
        return f"Cannot read git history for '{project}'."

    if not log.strip():
        _save_session(project)
        msg = f"No changes since {humanize_delta(since_dt)}. Context is fresh."
        if format == "json":
            return json.dumps({"project": project, "stale": False, "commits": [], "files": [], "message": msg})
        return msg

    commits: list[str] = []
    files: set[str] = set()
    current_commit: str | None = None
    for line in log.splitlines():
        line = line.strip()
        if not line:
            continue
        if _re.match(r"^[0-9a-f]{7} ", line):
            current_commit = redact(line)
            commits.append(current_commit)
        elif current_commit:
            files.add(line)

    _save_session(project)

    if format == "json":
        return json.dumps({
            "project": project,
            "stale": True,
            "since": humanize_delta(since_dt),
            "commits": commits[:10],
            "files": sorted(files)[:15],
        })

    out = [f"# {project} - drift since {humanize_delta(since_dt)}", ""]
    out.append(f"{len(commits)} new commit(s), {len(files)} file(s) touched\n")
    out.append("## New commits")
    out.extend(f"- {c}" for c in commits[:10])
    if files:
        out.append("\n## Files touched")
        out.extend(f"- {f}" for f in sorted(files)[:15])
    return "\n".join(out)


# ---------------------------------------------------------------------------
# get_predict
# ---------------------------------------------------------------------------

@mcp.tool()
def get_predict(project: str, file: str, format: str = "text") -> str:
    """Predict which files will also need changes based on historical co-change patterns.

    Call this before editing a file to understand implicit coupling.
    Use for "what else will I need to change if I edit <file>?"

    Args:
        project: Registered project name.
        file: File path relative to repo root (e.g. "soma/mcp.py").
        format: "text" (default) or "json".
    """
    from collections import Counter
    from git import InvalidGitRepositoryError, NoSuchPathError, Repo
    from git.exc import GitCommandError

    registry = load_registry(registry_path())
    if not registry:
        return "No projects registered. Run `soma init` first."
    entry = registry.get(project)
    if entry is None:
        known = ", ".join(sorted(registry.keys())[:10])
        return f"Unknown project '{project}'. Known projects: {known}"

    root = Path(entry["root"])
    try:
        repo = Repo(root)
        log = repo.git.log("--pretty=format:---COMMIT---", "--name-only")
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError, GitCommandNotFound):
        return f"Cannot read git history for '{project}'."

    commits_files: list[set[str]] = []
    current: set[str] = set()
    for line in log.splitlines():
        line = line.strip()
        if line == "---COMMIT---":
            if current:
                commits_files.append(current)
            current = set()
        elif line:
            current.add(line)
    if current:
        commits_files.append(current)

    target_commits = [c for c in commits_files if file in c]
    total = len(target_commits)
    if total == 0:
        return f"No commits found touching '{file}' in '{project}'."

    co_counts: Counter = Counter()
    for commit in target_commits:
        for f in commit:
            if f != file:
                co_counts[f] += 1

    results = [
        {"path": f, "count": count, "total": total, "pct": int(count / total * 100)}
        for f, count in co_counts.most_common(10)
        if count >= 2
    ]

    if format == "json":
        return json.dumps({"project": project, "file": file, "total_commits": total, "co_changes": results})

    if not results:
        return f"No strong co-change patterns for '{file}' ({total} commit(s) analysed)."

    out = [f"# Predict - {project} / {file}", f"\n{total} commit(s) touch this file.\n", "## Files that typically change together\n"]
    for r in results:
        confidence = "always" if r["pct"] >= 90 else "usually" if r["pct"] >= 60 else "sometimes"
        out.append(f"- {r['path']}  ({r['count']}/{total} - {confidence})")
    return "\n".join(out)
