# CLAUDE.md — SOMA v1 Agent Contract

## What This Project Is

SOMA (System Omniscient Memory Agent) v1 — a CLI tool that scans git repos on-demand
and generates project status, activity history, and compact LLM context summaries.

**The product is `soma context <project>`** — a ~500-token summary a developer pastes
into any LLM session so they never re-explain their project. Everything else supports that.

**One-line pitch:** "Your repos already remember everything. Now they can tell your AI."

## v1 Scope — HARD BOUNDARIES

### IN SCOPE (build only this)
- `soma init` — scan ~/ for .git roots, register to ~/.soma/projects.toml
- `soma status [project]` — last active, recent commits, files changed, branch
- `soma history [--markdown] [--days N]` — timestamped activity log per project/day
- `soma context <project> [--watch]` — compact context summary; --watch regenerates CLAUDE.md on change
- `pip install soma-cli` packaging

### OUT OF SCOPE (refuse to build, even if asked casually mid-session)
- ❌ Daemon / background processes (v1 is ON-DEMAND scanning only)
- ❌ LLM calls of any kind (v1 is pure heuristics + templates)
- ❌ Kuzu, sqlite-vec, any database (filesystem + TOML only)
- ❌ Shell logger, process watcher
- ❌ MCP server, TUI, graph visualization
- ❌ Completion percentages (use recency + blocker counts, never %)

If a task drifts out of scope, STOP and say: "This is Phase 1+ scope. Logged to docs/PHASE1_BACKLOG.md" and append it there.

## Architecture Rules

- Python 3.12, src layout: `soma/` package
- Data sources: `git log` (via gitpython) + file mtimes. The filesystem IS the daemon.
- All commands must respond in < 2 seconds on a machine with 10 repos
- CLI: typer + rich. No other UI.
- Config/state lives ONLY in `~/.soma/` (projects.toml). Never write inside watched repos
  except CLAUDE.md when --watch explicitly targets a repo.
- No network calls. Ever. Local-first is a product promise.

## Code Conventions

- Type hints everywhere, `pydantic` for the ProjectState model
- Every module < 300 lines; if bigger, split
- Errors: never stack-trace at the user. typer.Exit with a one-line rich message.
- Filter rules (ignore __pycache__, node_modules, .git/objects, build artifacts)
  live in ONE place: `soma/filters.py`

## The `soma context` Output Format (THE PRODUCT — do not freestyle this)

```
# {project} — Context Summary (generated {date} by SOMA)

**Branch:** {branch} | **Last active:** {humanized}
**Activity (7d):** {n} commits, {n} files changed

## Recent work
- {commit msg} ({relative time})  [max 5]

## Files in motion
- {path} ({last modified})  [max 8, by recency]

## Possible blockers
- {stale branch / old TODO / failing marker}  [heuristic, mark as "detected", never asserted]

## Suggested focus
{single line derived from most recent activity cluster}
```

Target: 350–600 tokens. If it exceeds 600, truncate file lists first, then commits.

## Testing Requirements

- `tests/test_filters.py` — filter rules (noise must be dropped)
- `tests/test_context.py` — context output stays within token budget, format stable
- `tests/test_detection.py` — project detection against a fixture tree
- Run `pytest` before declaring any task done. No exceptions.

## Definition of Done (v1)

- [ ] All 4 commands work on Harsha's real machine (Merops-X, AuraOS, Aran ISR, GATE repos)
- [ ] `soma context` output < 600 tokens, accurate vs. ground_truth.md
- [ ] pip installable, README with demo GIF
- [ ] Zero credentials/secrets possible in any output (no shell capture exists in v1 — keep it that way)

## Session Protocol

1. At session start: read this file + docs/ROADMAP.md + git log -10
2. State which v1 feature you're working on before writing code
3. Small commits, conventional messages: feat:/fix:/test:/docs:
4. At session end: update docs/SESSION_LOG.md with what was done + what's next
