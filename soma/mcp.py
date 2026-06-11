"""SOMA MCP server — exposes soma tools to Claude Desktop / Cursor.

Run with: soma mcp start
Install with: soma mcp install

No LLM calls, no network. Pure local git heuristics served over stdio.
"""
from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from soma.context import generate_context
from soma.detect import PROJECTS_FILE, load_registry
from soma.notes import load_notes
from soma.status import collect_statuses, get_status_safe, humanize_delta

mcp = FastMCP(
    name="soma",
    instructions=(
        "SOMA gives you live context from local git repos — "
        "no copy-paste needed. Call get_context before answering "
        "questions about a project's current state."
    ),
)


@mcp.tool()
def list_projects() -> str:
    """List all registered projects with their branch and last-active time."""
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        return "No projects registered. Run `soma init` first."
    statuses = collect_statuses(registry)
    lines = [f"{'Project':<28} {'Branch':<18} Last active"]
    lines.append("-" * 60)
    for s in statuses:
        lines.append(
            f"{s.name[:28]:<28} {s.branch[:18]:<18} {humanize_delta(s.last_active)}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_context(project: str) -> str:
    """Return SOMA context summary (~500 tokens) for a named project.

    This is the primary tool. Call it before answering questions about
    what a project is, what was recently worked on, or what to do next.
    """
    registry = load_registry(PROJECTS_FILE)
    if not registry:
        return "No projects registered. Run `soma init` first."
    entry = registry.get(project)
    if entry is None:
        known = ", ".join(sorted(registry.keys())[:10])
        return f"Unknown project '{project}'. Known projects: {known}"
    return generate_context(project, Path(entry["root"]))


@mcp.tool()
def search_projects(keyword: str) -> str:
    """Search a keyword across all project context summaries.

    Returns matching lines with project names. Case-insensitive.
    """
    import re  # noqa: PLC0415

    registry = load_registry(PROJECTS_FILE)
    if not registry:
        return "No projects registered."

    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    results: list[str] = []
    for name, entry in registry.items():
        try:
            text = generate_context(name, Path(entry["root"]))
        except Exception:  # git/OS/parse; skip repo rather than crash the MCP server
            continue
        hits = [line for line in text.splitlines() if pattern.search(line)]
        if hits:
            results.append(f"[{name}]")
            results.extend(f"  {line}" for line in hits[:5])

    if not results:
        return f"No matches for '{keyword}'."
    return "\n".join(results)


@mcp.tool()
def get_briefing() -> str:
    """Return a morning briefing — active, quiet, and dormant projects.

    Use this for broad questions like "what should I work on?" or
    "which projects have pending notes?".
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    registry = load_registry(PROJECTS_FILE)
    if not registry:
        return "No projects registered. Run `soma init` first."

    # Exclude archived
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

    lines: list[str] = [f"SOMA Briefing — {now.strftime('%Y-%m-%d %H:%M')} UTC", ""]
    if active:
        lines.append(f"ACTIVE ({len(active)})")
        for s in active:
            notes = load_notes(s.name)
            note_tag = f" [{len(notes)} note(s)]" if notes else ""
            lines.append(f"  {s.name} | {s.branch} | {s.commits_7d} commits this week{note_tag}")
    if quiet:
        lines.append(f"\nQUIET — no commits this week ({len(quiet)})")
        for s in quiet[:5]:
            lines.append(f"  {s.name} | {s.branch} | last active {humanize_delta(s.last_active, now)}")
    if dormant:
        lines.append(f"\nDORMANT >30d ({len(dormant)})")
        for s in dormant[:3]:
            lines.append(f"  {s.name} | last active {humanize_delta(s.last_active, now)}")

    return "\n".join(lines)
